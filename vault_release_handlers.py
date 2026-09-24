"""Integrated release candidate. Run as a separate MCP process; not live config.
Search, metadata and recall share one backend. No benchmark-specific routing.
"""
import re
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
sys.path.insert(0,str(Path(__file__).resolve().parent))
import vault_search_hardened as backend


def current_cron_state():
    """Read only public operational fields; never expose prompts or credentials."""
    import os,json
    from datetime import datetime,timezone
    home=Path(os.environ.get('HERMES_HOME',str(Path.home()/'.hermes')))
    path=home/'cron/jobs.json'
    data=json.loads(path.read_text())
    rows=data['jobs']
    if not isinstance(rows,list):raise ValueError('Invalid cron store')
    jobs=[{k:r.get(k) for k in ('name','enabled','state','schedule_display','next_run_at','last_run_at','last_status')} for r in rows if r.get('enabled') is True]
    return {'authority':str(path),'observed_at':datetime.now(timezone.utc).isoformat(),'active_jobs':jobs,'count':len(jobs)}


def blocker_page(limit,offset):
    excluded={'closed','resolved','done','complete','completed','archived'}
    docs=[d for d in backend.safe_documents() if (('/blockers/' in d['source'] or d['type'] in ('blocker','blocker-report')) and d['status'] not in excluded) or ('/05-PROJECT/' in d['source'] and d['status']=='blocked')]
    docs.sort(key=lambda d:(d['date'],d['source']),reverse=True)
    return {'results':[dict(backend.base.result(d,'blocker-metadata'),note_status=d['status'],note_date=d['date']) for d in docs[offset:offset+limit]],'total':len(docs),'offset':offset,'next_offset':offset+limit if offset+limit<len(docs) else None,'complete':False,'requires_live_verification':True,'state_authority':'historical-blocker-reports','warning':'Unclosed reports are evidence to verify, not proof a project remains blocked today.'}


def search(params):
    query=params.get('query','')
    top_k=params.get('top_k',15)
    mode=params.get('mode','broad')
    backend.validate(query,top_k,mode)
    offset=params.get('offset',0)
    if type(offset) is not int or offset<0:
        raise ValueError('offset must be a nonnegative integer')
    limit=min(top_k,5) if mode=='quick' else top_k
    intent=backend.metadata_intent(query)
    if intent and intent.get('status')=='blocked' and intent.get('kind')=='project':
        page=blocker_page(limit,offset)
        page.update(count=len(page['results']),query=query,mode=mode,degraded=[])
        return page
    if re.search(r'\bcron\b',query,re.I) and re.search(r'\b(active|aktif|current|sekarang)\b',query,re.I):
        # Scheduler truth must remain available even when the embedding service is down.
        try:
            response=backend.search_response(query,top_k,mode,strict=True)
        except Exception as exc:
            response={'query':query,'mode':mode,'results':[],'count':0,'complete':False,
                      'degraded':['historical-retrieval'],'state_authority':'unverified',
                      'retrieval_error':type(exc).__name__}
        try:
            response['live_state']=current_cron_state()
            response['state_authority']='scheduler-store'
            response['requires_live_verification']=False
            response['warning']='Enabled schedule configuration is not proof of successful execution; inspect last_status.'
        except (OSError,ValueError,KeyError,TypeError) as exc:
            response['live_state_error']=type(exc).__name__
            response['requires_live_verification']=True
            response['verification_source']='live scheduler'
        return response
    if intent:
        page=backend.metadata_page(**intent,limit=limit,offset=offset)
        page.update(count=len(page['results']),query=query,mode=mode,
                    requires_live_verification=bool(intent.get('status')),
                    verification_source='current project owner or project tracker' if intent.get('status') else None,
                    degraded=[],state_authority='historical-notes-only',
                    warning='Note metadata is not authoritative current scheduler or project state.',
                    scope='matching note metadata; follow next_offset until null')
        return page
    if offset:
        raise ValueError('offset is supported for metadata queries only')
    response=backend.search_response(query,top_k,mode,strict=True)
    if response['state_authority']=='historical-notes-only':
        response['requires_live_verification']=True
        response['verification_source']='live scheduler' if re.search(r'\bcron\b',query,re.I) else 'current project owner or project tracker'
    return response


def tag(params):
    tags=params.get('tags')
    if not isinstance(tags,list) or not tags or any(not isinstance(t,str) or not t.strip() for t in tags):
        raise ValueError('tags must be a nonempty array of nonempty strings')
    return backend.metadata_page(tags=tags,limit=params.get('top_k',20),offset=params.get('offset',0))


def date(params):
    if not isinstance(params.get('date'),str) or not params['date'].strip():
        raise ValueError('date is required')
    return backend.metadata_page(date=params['date'],limit=params.get('top_k',20),offset=params.get('offset',0))


def recall(params):
    from vault_recall_context import recall as build_context
    return build_context(params, backend)


def install(server):
    server.TOOLS.update(search_vault=search,search_by_tag=tag,search_by_date=date,recall=recall)
    replacements={
        'search_vault':{
            'description':'Ranked unique files, not exhaustive. quick caps at five. Metadata searches return total and next_offset; follow all pages. Historical notes do not establish live state.',
            'inputSchema':{'type':'object','properties':{'query':{'type':'string','maxLength':4096},'top_k':{'type':'integer','minimum':1,'maximum':50,'default':15},'mode':{'type':'string','enum':['broad','quick'],'default':'broad'},'offset':{'type':'integer','minimum':0,'default':0}},'required':['query']}},
        'recall':{
            'description':'Ranked seeds, exact one-hop links and project siblings. Evidence-text budget excludes metadata. Follow next_offset with snapshot; read partial_sources for full evidence. Candidate pagination is not exhaustive topic coverage.',
            'inputSchema':{'type':'object','properties':{'topic':{'type':'string','maxLength':4096},'top_k':{'type':'integer','minimum':1,'maximum':50,'default':20},'char_budget':{'type':'integer','minimum':1,'maximum':20000,'default':7000},'offset':{'type':'integer','minimum':0,'default':0},'snapshot':{'type':'string'}},'required':['topic']}}
    }
    for name,field,definition in [('search_by_tag','tags',{'type':'array','items':{'type':'string'},'minItems':1}),('search_by_date','date',{'type':'string'})]:
        replacements[name]={'description':'Read-only note metadata filter. Follow next_offset until null; historical note metadata is not live state.','inputSchema':{'type':'object','properties':{field:definition,'top_k':{'type':'integer','minimum':1,'maximum':50,'default':20},'offset':{'type':'integer','minimum':0,'default':0}},'required':[field]}}
    # Repeated install cannot duplicate catalog entries.
    definitions={d['name']:d for d in server.TOOL_DEFINITIONS}
    definitions.update({name:{'name':name,**definition} for name,definition in replacements.items()})
    server.TOOL_DEFINITIONS[:]=list(definitions.values())


"""Diagnostic replay of named forward schedules; never enabled in timing."""
import json
from pathlib import Path
PAIRS=json.loads(Path(__file__).with_name('pairs.json').read_text())
def rid_role(rid):
 p=rid.split('-')
 return 'T' if p[2]=='target' else p[4]
def prepare(scheduler):
    tagged=[r for r in scheduler.requests.values() if (r.kv_transfer_params or {}).get('lmcache.kv30_plan')]
    if not tagged:return None
    cfg=tagged[0].kv_transfer_params['lmcache.kv30_plan']
    key=tagged[0].request_id.split('-')[3]
    if getattr(scheduler,'kv30_key',None)!=key:
        scheduler.kv30_key=key;scheduler.kv30_step=0
        i,kind=cfg.split(':')
        scheduler.kv30_plan=PAIRS[int(i)][kind]['track']
        scheduler.kv30_ready=False
    if not scheduler.kv30_ready:
        target=next((r for r in tagged if rid_role(r.request_id)=='T'),None)
        if target and len(tagged)==5 and target.num_computed_tokens==4096 and (target.request_id in scheduler.finished_recving_kv_req_ids or target.status.name=='WAITING'):
            scheduler.kv30_ready=True
    if not scheduler.kv30_ready or scheduler.kv30_step>=len(scheduler.kv30_plan):
        return {}
    return {role:(start,count) for role,start,count,_ in scheduler.kv30_plan[scheduler.kv30_step]}
def advance(scheduler,counts,plan):
    if plan is None:return
    realized={rid_role(rid):n for rid,n in counts.items() if n}
    if not realized:return
    expected={k:n for k,(_,n) in plan.items()}
    assert realized==expected,(scheduler.kv30_step,expected,realized)
    scheduler.kv30_step+=1

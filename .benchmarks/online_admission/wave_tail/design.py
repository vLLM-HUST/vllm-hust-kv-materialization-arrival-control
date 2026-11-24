"""Fixed arrival-phase grid and tail-support calculations for #41."""
import math
from statistics import median
from collections import Counter
OFFSETS = (20,125,230,270,375,480,520,625,730,770,875,980)
def support(group):
    ordered=sorted(group,key=lambda r:r['target']['ttft_ms'])
    x=.95*(len(ordered)-1)
    lo,hi=math.floor(x),math.ceil(x)
    tail=ordered[lo:]
    return dict(p95=ordered[lo]['target']['ttft_ms']*(1-(x-lo))+ordered[hi]['target']['ttft_ms']*(x-lo),
                bracket=[ordered[i]['phase'] for i in (lo,hi)], offsets=sorted({r['phase'] for r in tail}),
                rows=[[r['phase'],r['target']['id'],r['target']['ttft_ms']] for r in tail])
def choose(rows):
    eligible=[ms for ms in OFFSETS if all(r['exact'] and r['exposure_ok'] for r in rows if r['phase']==ms)]
    selected=[r for r in rows if r['epoch']>=0 and r['phase'] in eligible]
    assert len(rows)==len(OFFSETS)*14 and len(selected)==len(eligible)*12
    if not eligible: return dict(eligible=[],gate=None,candidates=[],tails={})
    tails={a:support([r for r in selected if r['policy']==a]) for a in ('full','local')}
    gate='full' if tails['full']['p95']<=tails['local']['p95'] else 'local'
    candidates=sorted(set(tails['full']['offsets']+tails['local']['offsets']))
    return dict(eligible=eligible,gate=gate,candidates=candidates,tails=tails)
def verify(choice,rows):
    phases={}
    for ms in choice['candidates']:
        subset=[r for r in rows if r['phase']==ms]
        t={(r['epoch'],r['policy']):r['target']['ttft_ms'] for r in subset}
        assert len(t)==len(subset)==14
        diffs=[t[e,'local']-t[e,'full'] for e in range(6)]
        ok=all(r['exact'] and r['exposure_ok'] for r in subset)
        winner=('full' if min(diffs)>0 else 'local' if max(diffs)<0 else 'mixed') if ok else 'excluded'
        phases[str(ms)]=dict(winner=winner,paired_ms=diffs,median_ms=median(diffs),qualified=ok)
    def winners(offsets):
        return {phases[str(ms)]['winner'] for ms in offsets}
    offsets=choice['tails'][choice['gate']]['offsets'] if choice['gate'] else []
    return dict(phases=phases,promote={'full','local'}<=winners(offsets),gate_tail=offsets,
                either_tail_opposite={'full','local'}<=winners(choice['candidates']))

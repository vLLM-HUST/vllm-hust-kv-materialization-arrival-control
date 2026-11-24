import json, sys
from pathlib import Path
from statistics import median
HERE = Path(__file__).resolve().parent
def quant(vals):
    s=sorted(vals); idx=.95*(len(s)-1); i=int(idx)
    return s[i]+(idx-i)*(s[min(i+1,len(s)-1)]-s[i])
def rows(path):
    return [json.loads(s) for s in path.read_text().splitlines()]
def analyze(folder):
    groups={}
    data=rows(folder/'rows.jsonl')
    assert len(data)==112
    for cell in sorted({r['cell'] for r in data}):
        g=[r for r in data if r['cell']==cell]
        ok=all(r['exact'] and r['exposure_ok'] for r in g)
        diffs={}
        for ph in ('away','overlap'):
            t={(r['epoch'],r['policy']):r['target']['ttft_ms'] for r in g if r['phase']==ph}
            diffs[ph]=[t[e,'local']-t[e,'full'] for e in range(6)]
        signs={k:(1 if min(x)>0 else -1 if max(x)<0 else 0) for k,x in diffs.items()}
        p95={a:quant([r['target']['ttft_ms'] for r in g if r['epoch']>=0 and r['policy']==a]) for a in ('local','full')}
        groups[cell]=dict(exact_failures=sum(not r['exact'] for r in g),exposure_failures=sum(not r['exposure_ok'] for r in g),
            diffs_ms=diffs,median_diff_ms={k:median(x) for k,x in diffs.items()}, gate=2048 if p95['full']<=p95['local'] else 2176,
            endpoint_p95_ms=p95, promote=ok and signs['away']*signs['overlap']==-1)
    return groups
if __name__=='__main__':
    b=Path(sys.argv[1])
    info={str(n):analyze(b/f'axes-screen-{n}') for n in (4891,8544,12553)}
    (HERE/'screen.json').write_text(json.dumps(info,indent=2)+'\n')
    selected={n:{cell:c['gate'] for cell,c in cells.items() if c['promote']} for n,cells in info.items()}
    (HERE/'gates.json').write_text(json.dumps(selected,indent=2)+'\n')
    print(selected)

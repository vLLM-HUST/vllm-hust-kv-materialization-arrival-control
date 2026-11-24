"""Validate logged trial receipts and compute lifecycle-level policy comparisons."""
from collections import Counter
from pathlib import Path
import hashlib
import json
import math
from statistics import mean, stdev
import sys

from screen_analysis import rows, quant

def sha(data):
    return hashlib.sha256(data).hexdigest()

def ids_digest(seq):
    return sha(json.dumps(seq,separators=(',',':')).encode())

def receipts(folder, baseline):
    for name in ('build.sha256','args.txt'):
        assert (folder/name).read_bytes()==(baseline/name).read_bytes(),(folder,name)
    for name in ('npu-before.txt','npu-after.txt'):
        note=(folder/name).read_text()
        for d in (1,6):
            assert f'No running processes found in NPU {d}' in note,(folder,name,d)
    setup=rows(folder/'setup.jsonl')
    gold={r['stage']:r for r in setup if r['stage'].startswith('cold_')}
    mismatches=[]
    records=rows(folder/'rows.jsonl')
    for r in records:
        exact=True
        for row,ref in [(r['target'],'cold_target')]+[(p,'cold_peer') for p in r['peers']]:
            actual=row['output_ids']; expected=gold[ref]['output_ids']
            assert ids_digest(actual)==row['output_sha256'] and len(actual)==len(expected)
            if actual!=expected:
                exact=False
                pos=next(i for i,(x,y) in enumerate(zip(actual,expected),1) if x!=y)
                mismatches.append(dict(cell=r['cell'],phase=r['phase'],policy=r['policy'],epoch=r['epoch'],
                     id=row['id'],position=pos,expected=expected[pos-1],actual=actual[pos-1]))
        assert r['exact']==exact
    return dict(fixture=gold['cold_target']['fixture'],prompt_sha256=gold['cold_target']['prompt_sha256'],
                cold_sha256={k:r['output_sha256'] for k,r in gold.items()},targets=len(records),
                peers=sum(len(r['peers']) for r in records),mismatches=mismatches,
                exposure_failures=sum(not r['exposure_ok'] for r in records),raw_rows_sha256=sha((folder/'rows.jsonl').read_bytes())),records

def paired(ratios):
    x=[math.log(v) for v in ratios]
    mid=mean(x); rad=3.182446305284263*stdev(x)/2
    return [100*math.expm1(z) for z in (mid,mid-rad,mid+rad)]

def stats(g):
    assert Counter(r['phase'] for r in g)=={'away':8,'overlap':8}
    peers=[p for r in g for p in r['peers']]
    same=[p for p in peers if p['same_batch']]
    return dict(ttft=quant([r['target']['ttft_ms'] for r in g]), tpot=quant([p['tpot_ms'] for p in same]),
                all_tpot=quant([p['tpot_ms'] for p in peers]),same_n=len(same),all_n=len(peers),
                full_by_phase={ph:sum(r['decision']['used']==2048 for r in g if r['phase']==ph) for ph in ('away','overlap')})

def main(b,w):
    screen=json.loads((w/'screen.json').read_text())
    gates=json.loads((w/'gates.json').read_text())
    result=dict(protocol=(b/'discovery-axes-v1/protocol.md').read_text(),screen=screen,gates=gates,
                runs={},paired={},reserved_requests=0,build=(b/'token30-repeat-1/build.sha256').read_text())
    for n,cells in gates.items():
        runs=result['runs']
        f=b/f'axes-screen-{n}'
        runs[f.name],data=receipts(f,b/'token30-repeat-1')
        for cell in cells:
            result['paired'][f'{n}-{cell}']={'blocks':[]}
        if not cells: continue
        for i in range(1,5):
            f=b/f'axes-confirm-{n}-{i}'
            runs[f.name],data=receipts(f,b/'token30-repeat-1')
            for cell in cells:
                v=[r for r in data if r['cell']==cell]
                assert len(v)==36 and len({(r['epoch'],r['phase'],r['policy']) for r in v})==36
                ok=all(r['exact'] and r['exposure_ok'] for r in v)
                result['paired'][f'{n}-{cell}']['blocks'].append(dict(qualified=ok,idx=i,stats={
                    a:stats([r for r in v if r['policy']==a and r['epoch']>=0]) for a in ('peer','gate')} if ok else {}))
    for c in result['paired'].values():
        if all(z['qualified'] for z in c['blocks']):
            v={k:paired([z['stats']['peer'][k]/z['stats']['gate'][k] for z in c['blocks']]) for k in ('ttft','tpot','all_tpot')}
            c.update(estimates=v,joint=v['ttft'][2]<=-5 and v['tpot'][2]<=5)
        else: c.update(estimates=None,joint=False)
    (w/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main(*map(Path,sys.argv[1:]))

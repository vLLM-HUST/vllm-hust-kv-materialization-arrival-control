import hashlib,json,os
from pathlib import Path
import torch
from vllm.distributed.parallel_state import get_tp_group
def inspect_kv(runner, output):
    rank=get_tp_group().rank_in_group
    for idx,rid in enumerate(runner.input_batch.req_ids):
        plen=int(runner.input_batch.num_prompt_tokens[idx])
        start=int(runner.input_batch.num_computed_tokens_cpu[idx])
        end=start+output.num_scheduled_tokens[rid]
        is_seed=plen==4097 and 'kv41-back-' not in rid
        is_target=rid.startswith('cmpl-kv41-target-')
        if not (is_seed or is_target):continue
        kv=runner.kv_caches
        table=runner.input_batch.block_table[0].get_numpy_array()[idx]
        bs=kv[0][0].shape[1]
        assert bs>0 and 4096%bs==0,(bs,kv[0][0].shape)
        dst=Path(os.environ['KV41_CONTENTION_DIR'])
        if end>=4096 and not (dst/f'kv-{rid}-r{rank}.json').exists():
            # The ordinary cold chunk may stop exactly at 4096. The full
            # read is visible on the first following real target forward.
            blocks=torch.tensor(table[:4096//bs].copy(),dtype=torch.long,device=kv[0][0].device)
            hashes=[]
            for layer in kv:
                hashes.append([hashlib.sha256(x.index_select(0,blocks).contiguous().view(torch.uint8).cpu().numpy().tobytes()).hexdigest() for x in layer])
            (dst/f'kv-{rid}-r{rank}.json').write_text(json.dumps(hashes))
        if is_target and plen<=end<plen+32:
            block=int(table[(end-1)//bs])
            stack=torch.stack([torch.stack([x[block,(end-1)%bs] for x in layer]) for layer in kv])
            if not hasattr(runner,'_kv30_layers'):runner._kv30_layers={}
            hist=runner._kv30_layers.setdefault(rid,[]);hist.append(stack)
            if end==plen+31:
                torch.save(torch.stack(hist).cpu(),dst/f'layers-{rid}-r{rank}.pt')
                del runner._kv30_layers[rid]

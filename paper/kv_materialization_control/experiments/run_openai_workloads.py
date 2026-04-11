from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


WORKLOADS = {
    "short_low": {
        "num_requests": 12,
        "prompt_tokens": 256,
        "max_tokens": 96,
        "shared_prefix_tokens": 128,
        "families": 4,
        "concurrency": 2,
    },
    "long_medium": {
        "num_requests": 12,
        "prompt_tokens": 2048,
        "max_tokens": 128,
        "shared_prefix_tokens": 768,
        "families": 3,
        "concurrency": 3,
    },
}


@dataclass
class RequestResult:
    request_id: str
    family: int
    latency_s: float
    ok: bool
    http_status: int | None
    prompt_tokens_est: int
    completion_tokens_target: int
    error: str | None


def repeat_words(prefix: str, word: str, count: int) -> str:
    return prefix + " " + " ".join([word] * max(1, count))


def build_prompt(prompt_tokens: int, shared_prefix_tokens: int, family: int, request_id: str) -> list[dict[str, str]]:
    shared = repeat_words(f"family {family} shared context", "shared", shared_prefix_tokens)
    user_tokens = max(prompt_tokens - shared_prefix_tokens, 1)
    user = repeat_words(f"request {request_id} unique context", "unique", user_tokens)
    return [
        {"role": "system", "content": shared},
        {"role": "user", "content": user},
    ]


def send_request(base_url: str, model: str, request_id: str, family: int, prompt_tokens: int, shared_prefix_tokens: int, max_tokens: int) -> RequestResult:
    payload = {
        "model": model,
        "messages": build_prompt(prompt_tokens, shared_prefix_tokens, family, request_id),
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "stream": False,
    }
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        f"{base_url}/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    start = time.time()
    try:
        with urlopen(request, timeout=300) as response:
            json.loads(response.read().decode("utf-8", errors="replace"))
            return RequestResult(
                request_id=request_id,
                family=family,
                latency_s=time.time() - start,
                ok=True,
                http_status=response.status,
                prompt_tokens_est=prompt_tokens,
                completion_tokens_target=max_tokens,
                error=None,
            )
    except HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")
        return RequestResult(
            request_id=request_id,
            family=family,
            latency_s=time.time() - start,
            ok=False,
            http_status=exc.code,
            prompt_tokens_est=prompt_tokens,
            completion_tokens_target=max_tokens,
            error=message[:240],
        )
    except URLError as exc:
        return RequestResult(
            request_id=request_id,
            family=family,
            latency_s=time.time() - start,
            ok=False,
            http_status=None,
            prompt_tokens_est=prompt_tokens,
            completion_tokens_target=max_tokens,
            error=str(exc),
        )


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((q / 100.0) * (len(ordered) - 1)))))
    return ordered[index]


def summarize(results: list[RequestResult], started_at: float, finished_at: float) -> dict:
    ok = [result for result in results if result.ok]
    latencies_ms = [result.latency_s * 1000.0 for result in ok]
    output_tokens = sum(result.completion_tokens_target for result in ok)
    duration_s = max(1e-9, finished_at - started_at)
    return {
        "requests": len(results),
        "completed": len(ok),
        "mean_latency_ms": round(mean(latencies_ms), 3) if latencies_ms else 0.0,
        "p95_latency_ms": round(percentile(latencies_ms, 95), 3) if latencies_ms else 0.0,
        "request_throughput_rps": round(len(ok) / duration_s, 3),
        "output_throughput_toks": round(output_tokens / duration_s, 3),
        "failures": [asdict(result) for result in results if not result.ok],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a live workload against a vLLM OpenAI-compatible endpoint.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8011")
    parser.add_argument("--model", required=True)
    parser.add_argument("--workload", choices=sorted(WORKLOADS), default="short_low")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    config = dict(WORKLOADS[args.workload])
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    started_at = time.time()
    results: list[RequestResult] = []
    with ThreadPoolExecutor(max_workers=config["concurrency"]) as executor:
        futures = []
        for index in range(config["num_requests"]):
            futures.append(
                executor.submit(
                    send_request,
                    args.base_url,
                    args.model,
                    f"{args.workload}-{index}",
                    index % config["families"],
                    config["prompt_tokens"],
                    config["shared_prefix_tokens"],
                    config["max_tokens"],
                )
            )
            time.sleep(0.02)
        for future in as_completed(futures):
            results.append(future.result())
    finished_at = time.time()

    summary = summarize(results, started_at, finished_at)
    output_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    main()

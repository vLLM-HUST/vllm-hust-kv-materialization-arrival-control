from __future__ import annotations

import argparse
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from vllm_kv_materialization.shared_workloads import (
    DEFAULT_LIVE_WORKLOAD_CASE,
    build_live_workload,
)

LEGACY_WORKLOAD_ALIASES = {
    "short_low": DEFAULT_LIVE_WORKLOAD_CASE,
    "long_medium": "shared_scenario_rag_followup_long_context",
}


@dataclass
class RequestResult:
    request_id: str
    workload_case: str
    workload_family: str
    latency_s: float
    ttft_s: float | None
    ok: bool
    http_status: int | None
    prompt_tokens_est: int
    completion_tokens_target: int
    prompt_tokens_actual: int | None
    completion_tokens_actual: int | None
    started_at_utc: str
    finished_at_utc: str
    response_id: str | None
    finish_reason: str | None
    generated_text: str
    raw_events: list[dict]
    error: str | None


_RESULT_WRITE_LOCK = threading.Lock()


def utc_timestamp(timestamp_s: float | None = None) -> str:
    value = time.time() if timestamp_s is None else timestamp_s
    return (
        time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(value))
        + f".{int((value % 1) * 1_000_000):06d}Z"
    )


def build_api_url(base_url: str, path: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1"):
        return f"{normalized}/{path.lstrip('/')}"
    return f"{normalized}/v1/{path.lstrip('/')}"


def build_headers(api_key: str | None, user_agent: str | None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if user_agent:
        headers["User-Agent"] = user_agent
    return headers


def build_workload_headers(workload_request: object) -> dict[str, str]:
    return {
        "X-Request-Id": workload_request.request_id,
        "X-KV-Workload-Case": workload_request.workload_case,
        "X-KV-Workload-Family": workload_request.workload_family,
        "X-KV-Primary-Anchor-Id": workload_request.primary_anchor_id,
        "X-KV-Secondary-Anchor-Ids": ",".join(workload_request.secondary_anchor_ids),
        "X-KV-Shared-Prefix-Tokens": str(workload_request.shared_prefix_tokens),
        "X-KV-Reuse-Confidence": str(workload_request.reuse_confidence),
        "X-KV-Home-Rank": str(workload_request.home_rank),
        "X-KV-Turn-Index": str(workload_request.turn_index),
    }


def _usage_value(event: dict, name: str) -> int | None:
    usage = event.get("usage")
    if not isinstance(usage, dict) or usage.get(name) is None:
        return None
    return int(usage[name])


def _append_result(path: Path | None, result: RequestResult) -> None:
    if path is None:
        return
    payload = json.dumps(asdict(result), sort_keys=True)
    with _RESULT_WRITE_LOCK, path.open("a", encoding="utf-8") as handle:
        handle.write(payload)
        handle.write("\n")


def send_request(
    base_url: str,
    model: str,
    workload_request: object,
    api_key: str | None,
    user_agent: str | None,
    requests_output: Path | None = None,
) -> RequestResult:
    payload = {
        "model": model,
        "request_id": workload_request.request_id,
        "messages": [{"role": "user", "content": workload_request.prompt}],
        "max_tokens": workload_request.output_tokens,
        "temperature": 0.0,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        build_api_url(base_url, "chat/completions"),
        data=body,
        headers={
            **build_headers(api_key, user_agent),
            **build_workload_headers(workload_request),
        },
        method="POST",
    )

    started_wall = time.time()
    start = time.perf_counter()
    try:
        with urlopen(request, timeout=300) as response:
            raw_events: list[dict] = []
            generated_parts: list[str] = []
            ttft_s: float | None = None
            response_id: str | None = None
            finish_reason: str | None = None
            prompt_tokens_actual: int | None = None
            completion_tokens_actual: int | None = None
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                event = json.loads(data)
                raw_events.append(event)
                response_id = str(event.get("id") or response_id or "") or None
                choices = event.get("choices") or []
                for choice in choices:
                    delta = choice.get("delta") or {}
                    content = delta.get("content")
                    if content:
                        if ttft_s is None:
                            ttft_s = time.perf_counter() - start
                        generated_parts.append(str(content))
                    if choice.get("finish_reason") is not None:
                        finish_reason = str(choice["finish_reason"])
                prompt_tokens_actual = (
                    _usage_value(event, "prompt_tokens") or prompt_tokens_actual
                )
                completion_tokens_actual = (
                    _usage_value(event, "completion_tokens") or completion_tokens_actual
                )
            finished_wall = time.time()
            result = RequestResult(
                request_id=workload_request.request_id,
                workload_case=workload_request.workload_case,
                workload_family=workload_request.workload_family,
                latency_s=time.perf_counter() - start,
                ttft_s=ttft_s,
                ok=True,
                http_status=response.status,
                prompt_tokens_est=workload_request.prompt_tokens,
                completion_tokens_target=workload_request.output_tokens,
                prompt_tokens_actual=prompt_tokens_actual,
                completion_tokens_actual=completion_tokens_actual,
                started_at_utc=utc_timestamp(started_wall),
                finished_at_utc=utc_timestamp(finished_wall),
                response_id=response_id,
                finish_reason=finish_reason,
                generated_text="".join(generated_parts),
                raw_events=raw_events,
                error=None,
            )
            _append_result(requests_output, result)
            return result
    except HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")
        result = RequestResult(
            request_id=workload_request.request_id,
            workload_case=workload_request.workload_case,
            workload_family=workload_request.workload_family,
            latency_s=time.perf_counter() - start,
            ttft_s=None,
            ok=False,
            http_status=exc.code,
            prompt_tokens_est=workload_request.prompt_tokens,
            completion_tokens_target=workload_request.output_tokens,
            prompt_tokens_actual=None,
            completion_tokens_actual=None,
            started_at_utc=utc_timestamp(started_wall),
            finished_at_utc=utc_timestamp(),
            response_id=None,
            finish_reason=None,
            generated_text="",
            raw_events=[],
            error=message[:240],
        )
        _append_result(requests_output, result)
        return result
    except URLError as exc:
        result = RequestResult(
            request_id=workload_request.request_id,
            workload_case=workload_request.workload_case,
            workload_family=workload_request.workload_family,
            latency_s=time.perf_counter() - start,
            ttft_s=None,
            ok=False,
            http_status=None,
            prompt_tokens_est=workload_request.prompt_tokens,
            completion_tokens_target=workload_request.output_tokens,
            prompt_tokens_actual=None,
            completion_tokens_actual=None,
            started_at_utc=utc_timestamp(started_wall),
            finished_at_utc=utc_timestamp(),
            response_id=None,
            finish_reason=None,
            generated_text="",
            raw_events=[],
            error=str(exc),
        )
        _append_result(requests_output, result)
        return result


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((q / 100.0) * (len(ordered) - 1))))
    return ordered[index]


def summarize(
    results: list[RequestResult],
    started_at: float,
    finished_at: float,
    workload: object,
) -> dict:
    ok = [result for result in results if result.ok]
    latencies_ms = [result.latency_s * 1000.0 for result in ok]
    ttfts_ms = [result.ttft_s * 1000.0 for result in ok if result.ttft_s is not None]
    output_tokens = sum(
        result.completion_tokens_actual or result.completion_tokens_target
        for result in ok
    )
    duration_s = max(1e-9, finished_at - started_at)
    return {
        "workload_case": workload.case_id,
        "workload_label": workload.label,
        "dataset_name": workload.dataset_name,
        "workload_family": workload.workload_family,
        "request_rate": workload.request_rate,
        "concurrency": workload.concurrency,
        "requests": len(results),
        "completed": len(ok),
        "mean_latency_ms": round(mean(latencies_ms), 3) if latencies_ms else 0.0,
        "p95_latency_ms": round(percentile(latencies_ms, 95), 3)
        if latencies_ms
        else 0.0,
        "mean_ttft_ms": round(mean(ttfts_ms), 3) if ttfts_ms else 0.0,
        "p95_ttft_ms": round(percentile(ttfts_ms, 95), 3) if ttfts_ms else 0.0,
        "measurement_duration_s": duration_s,
        "completed_output_tokens": output_tokens,
        "request_throughput_rps": round(len(ok) / duration_s, 3),
        "output_throughput_toks": round(output_tokens / duration_s, 3),
        "failures": [asdict(result) for result in results if not result.ok],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a live workload against a vLLM OpenAI-compatible endpoint."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8011")
    parser.add_argument("--model", required=True)
    parser.add_argument("--workload-case", default=DEFAULT_LIVE_WORKLOAD_CASE)
    parser.add_argument(
        "--workload",
        choices=sorted(LEGACY_WORKLOAD_ALIASES),
        help="Deprecated alias for --workload-case.",
    )
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--request-rate", type=float)
    parser.add_argument("--concurrency", type=int)
    parser.add_argument("--max-output-tokens", type=int)
    parser.add_argument("--tokenizer")
    parser.add_argument("--api-key", default=os.environ.get("OPENAI_API_KEY", ""))
    parser.add_argument(
        "--user-agent",
        default=os.environ.get("OPENAI_HTTP_USER_AGENT", "python-httpx/0.28.1"),
    )
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--requests-output", help="JSONL path for every raw per-request result"
    )
    args = parser.parse_args()

    if args.workload and args.workload_case != DEFAULT_LIVE_WORKLOAD_CASE:
        parser.error(
            "use either --workload-case or the deprecated --workload alias, not both"
        )

    workload_case = LEGACY_WORKLOAD_ALIASES.get(args.workload, args.workload_case)
    workload = build_live_workload(
        workload_case,
        seed=args.seed,
        request_rate=args.request_rate,
        concurrency=args.concurrency,
        max_output_tokens=args.max_output_tokens,
        tokenizer_name_or_path=args.tokenizer,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    requests_output = (
        Path(args.requests_output)
        if args.requests_output
        else output_path.with_name(f"{output_path.stem}.requests.jsonl")
    )
    requests_output.parent.mkdir(parents=True, exist_ok=True)
    if requests_output.exists():
        parser.error(
            f"refusing to overwrite existing per-request output: {requests_output}"
        )

    started_at = time.time()
    results: list[RequestResult] = []
    with ThreadPoolExecutor(max_workers=workload.concurrency) as executor:
        futures = []
        for request in workload.requests:
            futures.append(
                executor.submit(
                    send_request,
                    args.base_url,
                    args.model,
                    request,
                    args.api_key or None,
                    args.user_agent or None,
                    requests_output,
                )
            )
            if request.arrival_gap_s > 0.0:
                time.sleep(request.arrival_gap_s)
        for future in as_completed(futures):
            results.append(future.result())
    finished_at = time.time()

    summary = summarize(results, started_at, finished_at, workload)
    summary["started_at_utc"] = utc_timestamp(started_at)
    summary["finished_at_utc"] = utc_timestamp(finished_at)
    summary["seed"] = args.seed
    summary["requests_output"] = str(requests_output)
    output_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )


if __name__ == "__main__":
    main()

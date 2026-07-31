from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

SCHEMA_VERSION = 1
CONDITIONS = {
    "baseline": {"floor_tokens": 256, "confidence_penalty_ms": 4.0},
    "tuned": {"floor_tokens": 128, "confidence_penalty_ms": 8.0},
}


def utc_timestamp(timestamp_s: float | None = None) -> str:
    value = time.time() if timestamp_s is None else timestamp_s
    return (
        time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(value))
        + f".{int((value % 1) * 1_000_000):06d}Z"
    )


def run_capture(command: list[str], cwd: Path) -> dict[str, object]:
    result = subprocess.run(
        command, cwd=cwd, text=True, capture_output=True, check=False
    )
    return {
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def git_state(path: Path) -> dict[str, object]:
    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(path), *args],
            text=True,
            capture_output=True,
            check=True,
        )
        return result.stdout.strip()

    status = git("status", "--porcelain=v1")
    return {
        "path": str(path.resolve()),
        "commit": git("rev-parse", "HEAD"),
        "branch": git("branch", "--show-current") or "DETACHED",
        "dirty": bool(status),
        "status_porcelain": status.splitlines(),
    }


def port_is_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def npu_is_idle(npu_info: str, device: int) -> bool:
    return f"No running processes found in NPU {device}" in npu_info


def wait_until_healthy(base_url: str, server: subprocess.Popen, timeout_s: int) -> None:
    deadline = time.monotonic() + timeout_s
    last_error = "not attempted"
    while time.monotonic() < deadline:
        if server.poll() is not None:
            raise RuntimeError(
                f"server exited before health check, returncode={server.returncode}"
            )
        try:
            with urlopen(f"{base_url.rstrip('/')}/v1/models", timeout=5) as response:
                if response.status == 200:
                    return
                last_error = f"HTTP {response.status}"
        except (OSError, URLError) as exc:
            last_error = str(exc)
        time.sleep(2)
    raise TimeoutError(
        f"server health check timed out after {timeout_s}s: {last_error}"
    )


def stop_process_group(
    process: subprocess.Popen, timeout_s: int = 90
) -> dict[str, object]:
    if process.poll() is not None:
        return {
            "already_exited": True,
            "returncode": process.returncode,
            "forced": False,
        }
    os.killpg(process.pid, signal.SIGTERM)
    try:
        returncode = process.wait(timeout=timeout_s)
        return {"already_exited": False, "returncode": returncode, "forced": False}
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        returncode = process.wait(timeout=30)
        return {"already_exited": False, "returncode": returncode, "forced": True}


def write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one independently auditable online service lifecycle."
    )
    parser.add_argument("--bundle-dir", required=True)
    parser.add_argument("--workload-case", required=True)
    parser.add_argument("--condition", choices=sorted(CONDITIONS), required=True)
    parser.add_argument("--seam", choices=("old", "segmented"), required=True)
    parser.add_argument("--carrier-root", default="vendor/vllm")
    parser.add_argument("--model", required=True)
    parser.add_argument("--served-model-name", default="Qwen2.5-7B-Instruct")
    parser.add_argument("--device", type=int, default=7)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8011)
    parser.add_argument("--block-size", type=int, default=16)
    parser.add_argument("--max-model-len", type=int, default=32768)
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.85)
    parser.add_argument("--request-rate", type=float, default=24.0)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--max-output-tokens", type=int, default=64)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--env-name", default="vllm-kv-materialization-exp")
    parser.add_argument("--health-timeout-s", type=int, default=900)
    parser.add_argument("--evidence-label", default="real-online/formal-matrix")
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Development only; formal and dry runs must stay clean",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    repo_root = Path(__file__).resolve().parents[3]
    bundle_dir = Path(args.bundle_dir).resolve()
    carrier_root = (
        (repo_root / args.carrier_root).resolve()
        if not Path(args.carrier_root).is_absolute()
        else Path(args.carrier_root).resolve()
    )
    model = Path(args.model).resolve()
    if bundle_dir.exists():
        raise SystemExit(
            f"refusing to overwrite existing bundle directory: {bundle_dir}"
        )
    # Capture cleanliness before creating an in-repository evidence directory.
    parent_state = git_state(repo_root)
    carrier_state = git_state(carrier_root)
    bundle_dir.mkdir(parents=True)

    manifest_path = bundle_dir / "environment_manifest.json"
    run_manifest_path = bundle_dir / "run_manifest.json"
    failed_path = bundle_dir / "FAILED.txt"
    blocked_path = bundle_dir / "BLOCKED.txt"
    server_log_path = bundle_dir / "server.log"
    client_log_path = bundle_dir / "client.log"
    runtime_observations_path = bundle_dir / "runtime_observations.jsonl"
    summary_path = bundle_dir / "request_summary.json"
    requests_path = bundle_dir / "request_results.jsonl"
    base_url = f"http://{args.host}:{args.port}"
    started_at = time.time()
    server: subprocess.Popen | None = None
    cleanup: dict[str, object] = {}

    condition = CONDITIONS[args.condition]
    npu_check = run_capture(["npu-smi", "info"], repo_root)
    workload_direct_url = (
        Path(sys.prefix)
        / "lib"
        / f"python{sys.version_info.major}.{sys.version_info.minor}"
        / "site-packages"
        / "llm_serving_workloads-0.1.0.dist-info"
        / "direct_url.json"
    )
    workload_source = (
        json.loads(workload_direct_url.read_text())
        if workload_direct_url.exists()
        else None
    )
    versions = run_capture(
        [sys.executable, "-m", "pip", "list", "--format=json"], repo_root
    )
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": utc_timestamp(started_at),
        "evidence_label": args.evidence_label,
        "host_launcher": "repo-local shell lifecycle runner",
        "container": None,
        "parent": parent_state,
        "carrier": carrier_state,
        "workload_source": workload_source,
        "python_executable": sys.executable,
        "conda_prefix": os.environ.get("CONDA_PREFIX"),
        "conda_environment": args.env_name,
        "versions": versions,
        "npu_info": npu_check,
        "model": str(model),
        "model_config": json.loads((model / "config.json").read_text()),
        "device": args.device,
        "host": args.host,
        "port": args.port,
        "execution_mode_requested": "graph-capable default; --enforce-eager absent",
        "execution_mode_effective_source": "server.log",
        "block_size": args.block_size,
        "max_model_len": args.max_model_len,
    }
    write_json(manifest_path, manifest)

    try:
        blocking_reasons = []
        if npu_check["returncode"] != 0 or not npu_is_idle(
            str(npu_check["stdout"]), args.device
        ):
            blocking_reasons.append(f"NPU {args.device} is not confirmed idle")
        if not port_is_free(args.host, args.port):
            blocking_reasons.append(f"port {args.host}:{args.port} is occupied")
        if (parent_state["dirty"] or carrier_state["dirty"]) and not args.allow_dirty:
            blocking_reasons.append("parent or carrier worktree is dirty")
        if not model.joinpath("config.json").is_file():
            blocking_reasons.append(f"model config missing: {model / 'config.json'}")
        if blocking_reasons:
            blocked_path.write_text(
                "\n".join(blocking_reasons) + "\n", encoding="utf-8"
            )
            return 3

        server_env = os.environ.copy()
        server_env.update(
            {
                "ASCEND_RT_VISIBLE_DEVICES": str(args.device),
                "ENV_NAME": args.env_name,
                "MODEL": str(model),
                "SERVED_MODEL_NAME": args.served_model_name,
                "WORKLOAD_CASE": args.workload_case,
                "HOST": args.host,
                "PORT": str(args.port),
                "ENABLE_PLUGIN": "1",
                "MAX_MODEL_LEN": str(args.max_model_len),
                "BLOCK_SIZE": str(args.block_size),
                "GPU_MEMORY_UTILIZATION": str(args.gpu_memory_utilization),
                "VLLM_KV_PARTIAL_REUSE_FLOOR_TOKENS": str(condition["floor_tokens"]),
                "VLLM_KV_CONFIDENCE_PENALTY_MS": str(
                    condition["confidence_penalty_ms"]
                ),
                "VLLM_KV_RUNTIME_BLOCK_SIZE": str(args.block_size),
                "VLLM_KV_RUNTIME_HASH_BLOCK_SIZE": str(args.block_size),
                "VLLM_KV_MATERIALIZATION_LOG_PATH": str(runtime_observations_path),
                "VLLM_DEBUG_PREFIX_CACHE_TRACE": "1",
                "CARRIER_VLLM_HUST_ROOT": str(carrier_root),
            }
        )
        server_command = [
            "bash",
            "paper/kv_materialization_control/experiments/launch_vllm_kv_materialization_server.sh",
            "--tensor-parallel-size",
            "1",
        ]
        client_command = [
            sys.executable,
            "paper/kv_materialization_control/experiments/run_openai_workloads.py",
            "--base-url",
            base_url,
            "--model",
            args.served_model_name,
            "--tokenizer",
            str(model),
            "--workload-case",
            args.workload_case,
            "--seed",
            str(args.seed),
            "--request-rate",
            str(args.request_rate),
            "--concurrency",
            str(args.concurrency),
            "--max-output-tokens",
            str(args.max_output_tokens),
            "--output",
            str(summary_path),
            "--requests-output",
            str(requests_path),
        ]
        run_manifest = {
            "schema_version": SCHEMA_VERSION,
            "status": "starting",
            "started_at_utc": utc_timestamp(),
            "evidence_label": args.evidence_label,
            "workload_case": args.workload_case,
            "seam": args.seam,
            "condition": args.condition,
            "condition_knobs": condition,
            "server_command": server_command,
            "server_environment": {
                key: server_env[key]
                for key in sorted(server_env)
                if key.startswith(
                    (
                        "ASCEND_",
                        "VLLM_",
                        "MODEL",
                        "SERVED_",
                        "WORKLOAD_",
                        "BLOCK_",
                        "MAX_MODEL_",
                        "GPU_MEMORY_",
                        "HOST",
                        "PORT",
                        "ENV_NAME",
                        "CARRIER_",
                    )
                )
            },
            "client_command": client_command,
        }
        write_json(run_manifest_path, run_manifest)

        with server_log_path.open("w", encoding="utf-8") as server_log:
            server = subprocess.Popen(
                server_command,
                cwd=repo_root,
                env=server_env,
                stdout=server_log,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=True,
            )
        wait_until_healthy(base_url, server, args.health_timeout_s)
        client_env = os.environ.copy()
        client_env["PYTHONPATH"] = str(repo_root / "src")
        with client_log_path.open("w", encoding="utf-8") as client_log:
            client_result = subprocess.run(
                client_command,
                cwd=repo_root,
                env=client_env,
                stdout=client_log,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
        if client_result.returncode != 0:
            raise RuntimeError(
                f"workload driver failed with returncode={client_result.returncode}"
            )
        run_manifest["status"] = "completed"
        run_manifest["finished_at_utc"] = utc_timestamp()
        run_manifest["client_returncode"] = client_result.returncode
        write_json(run_manifest_path, run_manifest)
        return 0
    except Exception as exc:  # noqa: BLE001 - every failure must be preserved in the bundle
        failed_path.write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
        if run_manifest_path.exists():
            run_manifest = json.loads(run_manifest_path.read_text())
            run_manifest.update(
                {
                    "status": "failed",
                    "finished_at_utc": utc_timestamp(),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            write_json(run_manifest_path, run_manifest)
        return 1
    finally:
        if server is not None:
            cleanup["server"] = stop_process_group(server)
        cleanup["port_free_after"] = port_is_free(args.host, args.port)
        final_npu = run_capture(["npu-smi", "info"], repo_root)
        cleanup["npu_info_after"] = final_npu
        cleanup["device_idle_after"] = npu_is_idle(
            str(final_npu["stdout"]), args.device
        )
        cleanup["finished_at_utc"] = utc_timestamp()
        write_json(bundle_dir / "cleanup.json", cleanup)
        if manifest_path.exists() and server_log_path.exists():
            final_manifest = json.loads(manifest_path.read_text())
            graph_evidence = [
                line
                for line in server_log_path.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()
                if any(
                    token in line.lower()
                    for token in (
                        "cudagraph",
                        "graph mode",
                        "enforce_eager",
                        "enforce eager",
                    )
                )
            ]
            final_manifest["execution_mode_evidence"] = graph_evidence
            final_manifest["cleanup_path"] = str(bundle_dir / "cleanup.json")
            write_json(manifest_path, final_manifest)


if __name__ == "__main__":
    raise SystemExit(main())

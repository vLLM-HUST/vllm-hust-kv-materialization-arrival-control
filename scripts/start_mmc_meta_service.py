#!/usr/bin/env python3
"""Start the MMC meta service required by the AscendStore memcache backend.

The memcache backend (use_layerwise=True + backend=memcache) requires a
standalone MMC meta service listening on 127.0.0.1:5000 (meta) and
127.0.0.1:6000 (config store). This script starts it in the foreground; run it
in a detached process before launching vLLM:

    setsid python3 scripts/start_mmc_meta_service.py > /tmp/mmc_meta.log 2>&1 &
"""

from __future__ import annotations

import argparse

import memcache_hybrid  # noqa: F401  (loads the native library and sys.path)
from memcache_hybrid import MetaConfig, MetaService


def main() -> None:
    parser = argparse.ArgumentParser(description="Start a local MMC meta service.")
    parser.add_argument("--meta-port", type=int, default=5000)
    parser.add_argument("--config-store-port", type=int, default=6000)
    parser.add_argument("--metrics-port", type=int, default=8000)
    args = parser.parse_args()
    cfg = MetaConfig()
    cfg.config_store_url = f"tcp://127.0.0.1:{args.config_store_port}"
    cfg.meta_service_url = f"tcp://127.0.0.1:{args.meta_port}"
    cfg.metrics_url = f"http://127.0.0.1:{args.metrics_port}"
    cfg.log_level = "info"

    rc = MetaService.setup(cfg)
    if rc != 0:
        raise SystemExit(f"MetaService.setup failed: rc={rc}")
    print("MMC meta service setup ok; starting (blocking) ...", flush=True)
    MetaService.main()


if __name__ == "__main__":
    main()

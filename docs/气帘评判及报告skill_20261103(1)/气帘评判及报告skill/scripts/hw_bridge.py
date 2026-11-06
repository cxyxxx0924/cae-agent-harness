#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""HyperWorks 2026 live-bridge client (raw TCP socket protocol).

This is the same transport the hyperworks MCP stdio server uses. The MCP stdio
server is frequently NOT spawned by the host, but the HyperWorks GUI Extension
(live bridge) is up on 127.0.0.1:48761, so we talk to it directly.

Usage:
    python hw_bridge.py ping
    python hw_bridge.py get_capabilities
    python hw_bridge.py get_session_info
    python hw_bridge.py <method> '<json-params>'

Common methods used for curtain evaluation:
    postprocess_hyperview_result  -- contour a result type and screenshot
    extract_hypergraph_time_history -- node time-history to csv/png

Environment:
    HW_BRIDGE_TIMEOUT  (seconds; default 60; use 600 for big H3D loads)

The token + port are read automatically from the HyperWorksMCP Extension
bridge config at:
    C:\\Users\\hekie\\AppData\\Local\\HyperWorksMCP\\bridge.json
"""
import json
import os
import sys

# Make the MCP package importable so we can reuse its battle-tested client.
VENV = r"C:\Users\hekie\.workbuddy\binaries\python\envs\hyperworks-mcp\Lib\site-packages"
if VENV not in sys.path:
    sys.path.insert(0, VENV)

from hyperworks_mcp.live_bridge import LiveBridgeClient  # noqa: E402


def main() -> int:
    client = LiveBridgeClient()
    if len(sys.argv) < 2:
        print("usage: hw_bridge.py <method> [json-params]", file=sys.stderr)
        return 2
    method = sys.argv[1]
    params = {}
    if len(sys.argv) >= 3:
        params = json.loads(sys.argv[2])
    timeout = float(os.environ.get("HW_BRIDGE_TIMEOUT", "60"))
    try:
        if method == "ping":
            result = client.call("ping", timeout=timeout)
        else:
            result = client.call(method, params, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

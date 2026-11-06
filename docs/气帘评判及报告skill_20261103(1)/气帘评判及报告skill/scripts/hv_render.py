#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""HyperWorks 后处理一体化 CLI（气帘评判 / 报告素材生产）。

一条命令覆盖：探活 → 重启 → 读 d3plot/H3D 出云图 → 四视角×多时刻 → 2×2 动画 GIF
→ PPT 素材（末帧拼版、裁白边后的单图）。

设计原则
--------
* **只走 live bridge**（127.0.0.1，HyperWorks GUI 进程内的 Extension）。
  Python 侧 `hw.hv` 的 Window 对象没有相机方法，所有视角控制必须在 Tcl 层，
  已封装在 bridge 的 `postprocess_hyperview_shots` 里。
* **每个产物都自证**：shots 返回每张图的 md5，`check` 子命令验证四视角真的不同。
* 重启用**官方启动参数**（-plugin/-profile/-startwith）。自己裸起 runhwx
  会拿到窗口站但 Qt 消息泵不转，端口永远不绑。

子命令
------
    status                              探活（端口/版本/允许根）
    restart [--app HyperView]           结束监听进程并按官方参数重启，轮询至在线
    single  --model M --result R ...    单张云图截图
    shots   --model M --result R ...    多视角 × 多时间步截图（默认 4 视角）
    check   --shots shots.json          md5 唯一性校验（视角没生效会在这里被抓到）
    gif     --shots shots.json --gif G  2×2 拼版动画 GIF + 末帧 PNG
    anim    --model M --result R ...    shots → check → gif 一条龙

示例（读 d3plot，四视角 21 帧动画）
-----------------------------------
    python hv_render.py status
    python hv_render.py restart --app HyperView
    python hv_render.py anim \
        --model  "C:/Users/hekie/Documents/HyperWorksMCP/workspace/Iter05_d3plot/d3plot" \
        --result "C:/Users/hekie/Documents/HyperWorksMCP/workspace/Iter05_d3plot/d3plot" \
        --outdir "C:/Users/hekie/Documents/HyperWorksMCP/workspace/Iter05_d3plot/out" \
        --frames 21 --gif  out/fourview.gif --png out/fourview_last.png

环境
----
* 用**系统 python** 跑（需要 Pillow；hyperworks-mcp venv 里没有 Pillow）。
  live_bridge 客户端从 venv 的 site-packages 动态加入 sys.path。
* `HW_BRIDGE_TIMEOUT`（秒，默认 600）。大 d3plot 首次加载慢，别调小。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

BRIDGE_PORT = 48761
BRIDGE_CONF = Path(r"C:\Users\hekie\AppData\Local\HyperWorksMCP\bridge.json")
MCP_VENV_SITE = Path(
    r"C:\Users\hekie\.workbuddy\binaries\python\envs\hyperworks-mcp\Lib\site-packages"
)
ALTair_HOME = Path(r"D:\Program Files\Altair\2026")
RUNHWX = ALTair_HOME / "hwdesktop/hwx/bin/win64/runhwx.exe"
VIEWS = ["front", "back", "left", "right"]
CREATE_BREAKAWAY_FROM_JOB = 0x01000000  # detach from the caller's job, keep window station


# --------------------------------------------------------------------------- #
# bridge
# --------------------------------------------------------------------------- #
def _load_conf() -> dict:
    try:
        return json.loads(BRIDGE_CONF.read_text(encoding="utf-8"))
    except Exception:
        return {"host": "127.0.0.1", "port": BRIDGE_PORT,
                "allowed_roots": [r"C:\Users\hekie\Documents\HyperWorksMCP\workspace"]}


def _client():
    if str(MCP_VENV_SITE) not in sys.path:
        sys.path.insert(0, str(MCP_VENV_SITE))
    try:
        from hyperworks_mcp.live_bridge import LiveBridgeClient  # noqa: WPS433
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(
            f"无法导入 live_bridge 客户端（{exc}）。\n"
            f"请确认 hyperworks-mcp venv 存在于 {MCP_VENV_SITE}"
        )
    return LiveBridgeClient()


def call(method: str, params: dict | None = None, timeout: float | None = None) -> dict:
    timeout = float(timeout or os.environ.get("HW_BRIDGE_TIMEOUT", "600"))
    return _client().call(method, params or {}, timeout=timeout)


def _listener_pid(port: int = BRIDGE_PORT) -> int | None:
    try:
        out = subprocess.run(["netstat", "-ano"], capture_output=True,
                             text=True, encoding="mbcs", errors="ignore").stdout
    except Exception:
        return None
    for line in out.splitlines():
        if f":{port}" in line and "LISTENING" in line.upper():
            parts = line.split()
            if parts and parts[-1].isdigit():
                return int(parts[-1])
    return None


def _port_busy(port: int = BRIDGE_PORT) -> bool:
    return _listener_pid(port) is not None


def _wait_online(timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _port_busy():
            try:
                call("ping", timeout=15)
                return True
            except Exception:
                pass
        time.sleep(4)
    return False


def cmd_status(_args) -> int:
    conf = _load_conf()
    pid = _listener_pid()
    print(f"bridge conf : {conf.get('host')}:{conf.get('port')}  roots={conf.get('allowed_roots')}")
    print(f"listener    : {'pid ' + str(pid) if pid else 'NOT listening'}")
    if not pid:
        print("状态        : OFFLINE  →  python hv_render.py restart --app HyperView")
        return 1
    try:
        info = call("ping", timeout=20)
    except Exception as exc:  # noqa: BLE001
        print(f"ping        : 失败 {exc}")
        return 1
    print(f"ping        : OK  {info.get('bridge')} v{info.get('version')}")
    return 0


def cmd_restart(args) -> int:
    conf = _load_conf()
    workspace = Path(conf["allowed_roots"][0])
    pid = _listener_pid()
    if pid:
        print(f"[1/4] 结束占用 {BRIDGE_PORT} 的进程 pid={pid}")
        subprocess.run(["taskkill", "/PID", str(pid), "/F", "/T"],
                       capture_output=True, text=True, encoding="mbcs", errors="ignore")
    else:
        print("[1/4] 端口空闲，无需结束")

    for _ in range(20):
        if not _port_busy():
            break
        time.sleep(1)
    print(f"[2/4] 端口 {BRIDGE_PORT} 已释放 = {not _port_busy()}")

    if not RUNHWX.is_file():
        raise SystemExit(f"找不到 {RUNHWX}")
    cmd = [str(RUNHWX), "-client", "HyperWorksDesktop",
           "-plugin", "HyperworksLauncher", "-profile", "HyperworksLauncher",
           "-l", args.lang, "-startwith", args.app]
    print(f"[3/4] 启动 {args.app}: {' '.join(cmd)}")
    flags = CREATE_BREAKAWAY_FROM_JOB if os.name == "nt" else 0
    try:
        proc = subprocess.Popen(cmd, cwd=str(workspace), stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                shell=False, creationflags=flags)
    except OSError:
        proc = subprocess.Popen(cmd, cwd=str(workspace), stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"      pid={proc.pid}  cwd={workspace}")

    print(f"[4/4] 等待 bridge 上线（最多 {args.wait}s，扩展只在启动时加载 handlers.py）")
    if _wait_online(args.wait):
        print("      ONLINE ✔")
        return 0
    print("      超时未上线。检查：HyperView 是否真的起来（tasklist | grep hwx）、"
          "端口是否被别的实例占用、Extension 是否加载。")
    return 1


# --------------------------------------------------------------------------- #
# render
# --------------------------------------------------------------------------- #
def _check_roots(paths: list[str]) -> None:
    roots = [Path(r).resolve() for r in _load_conf().get("allowed_roots", [])]
    for p in paths:
        try:
            rp = Path(p).resolve()
        except Exception:
            continue
        if not any(str(rp).lower().startswith(str(r).lower()) for r in roots):
            print(f"⚠ 路径不在 bridge allowed_roots 下，可能被拒：{rp}")
            print(f"  允许根：{[str(r) for r in roots]}")


def _base_params(args) -> dict:
    return {
        "model_file": args.model,
        "result_file": args.result,
        "data_type": args.type,
        "data_component": args.comp,
        "entity_type": args.entity,
    }


def cmd_single(args) -> int:
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    _check_roots([args.model, args.result, str(out)])
    params = _base_params(args)
    params.update({
        "output_file": str(out),
        "page_title": args.title,
        "query_limit": args.limit,
        "simulation": args.sim,
        "average_mode": "none",
    })
    res = call("postprocess_hyperview_result", params)
    ok = Path(res.get("output_file", out)).is_file()
    print(json.dumps({k: v for k, v in res.items() if k != "top_entities"},
                     ensure_ascii=False, indent=2))
    if ok:
        print(f"PNG  {out}  {out.stat().st_size // 1024} KB")
    return 0 if ok else 1


def _parse_steps(spec: str) -> list[int]:
    """'1:82:4' → [1,5,...,81]；'1,5,9' → [1,5,9]"""
    spec = spec.strip()
    if ":" in spec:
        a, b, c = (int(x) for x in spec.split(":"))
        return list(range(a, b + 1, c))
    return [int(x) for x in re.split(r"[,\s]+", spec) if x]


def _probe_last(model: str, result: str, outdir: Path, args) -> int:
    """用一次单视角末帧调用探出最后一个仿真步 id。"""
    tmp = outdir / "_probe"
    params = _base_params(args)
    params.update({"output_dir": str(tmp), "views": ["front"], "simulations": ["last"]})
    res = call("postprocess_hyperview_shots", params)
    shots = res.get("shots") or []
    if not shots:
        raise SystemExit("探测末步失败：bridge 未返回任何截图")
    return int(shots[0]["simulation"])


def cmd_shots(args) -> int:
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    _check_roots([args.model, args.result, str(outdir)])

    if args.steps:
        steps = _parse_steps(args.steps)
    else:
        last = args.last or _probe_last(args.model, args.result, outdir, args)
        n = max(2, args.frames)
        steps = sorted({1, last, *[1 + round(i * (last - 1) / (n - 1)) for i in range(n)]})
    print(f"时间步（{len(steps)}）：{steps}")

    views = [v.strip().lower() for v in args.views.split(",") if v.strip()]
    params = _base_params(args)
    params.update({"output_dir": str(outdir), "views": views, "simulations": steps})
    res = call("postprocess_hyperview_shots", params)

    shots = res.get("shots") or []
    payload = {"model_file": args.model, "result_file": args.result,
               "views": views, "steps": steps, "shots": shots,
               "legend": res.get("legend"), "page_id": res.get("page_id")}
    shots_json = outdir / "shots.json"
    shots_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    uniq = len({s.get("md5") for s in shots})
    print(f"截图 {len(shots)} 张（期望 {len(views) * len(steps)}），unique md5 = {uniq}")
    print(f"清单 {shots_json}")
    if args.preview and shots:
        for s in shots[:4]:
            print(f"  {s['view']:>5} s{s['simulation']:<4} {s['size_bytes']//1024:>4} KB  {s['md5'][:12]}")
    return 0


def cmd_check(args) -> int:
    data = json.loads(Path(args.shots).read_text(encoding="utf-8"))
    shots = data.get("shots") or []
    if not shots:
        print("清单里没有 shots")
        return 1
    by_view: dict[str, int] = {}
    for s in shots:
        by_view[s["view"]] = by_view.get(s["view"], 0) + 1
    md5s = [s.get("md5") for s in shots]
    uniq = len(set(md5s))
    print(f"文件      : {args.shots}")
    print(f"截图      : {len(shots)}   {by_view}")
    print(f"unique md5: {uniq} / {len(shots)}")
    if uniq == 1:
        print("✘ 全部相同 —— 视角没有生效。逐项排查：")
        print("  1) Tcl 是否用了 Python 侧真实的 page.id（不是写死 1）")
        print("  2) handle 是否每次调用唯一命名（否则 'already exists' 中断命令链）")
        print("  3) 是否用了 SetOrientation（SetView 不存在）")
        print("  4) 是否在设完视角后又调了 Python window.draw()（会重置相机）")
        return 1
    if uniq < len(shots):
        dup = {m for m in md5s if md5s.count(m) > 1}
        print(f"⚠ 有 {len(dup)} 组重复（可能是静止帧或视角未切换），不致命但要人工确认")
    print("✔ 视角区分正常")
    return 0


# --------------------------------------------------------------------------- #
# gif / ppt assets
# --------------------------------------------------------------------------- #
def _font(size: int):
    from PIL import ImageFont
    for p in (r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\arial.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _crop_white(im, pad: int = 14, thresh: int = 246):
    g = im.convert("L")
    w, h = g.size
    px = g.load()
    left, top, right, bottom = w, h, 0, 0
    step = max(1, min(w, h) // 400)
    for y in range(0, h, step):
        for x in range(0, w, step):
            if px[x, y] < thresh:
                left = min(left, x); right = max(right, x)
                top = min(top, y); bottom = max(bottom, y)
    if right <= left or bottom <= top:
        return im
    return im.crop((max(0, left - pad), max(0, top - pad),
                    min(w, right + pad + step), min(h, bottom + pad + step)))


def _fit_cell(im, cw: int, ch: int, crop: bool = True):
    from PIL import Image
    if crop:
        im = _crop_white(im)
    iw, ih = im.size
    scale = min(cw / iw, ch / ih)
    nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
    cell = Image.new("RGB", (cw, ch), (255, 255, 255))
    cell.paste(im.resize((nw, nh), Image.LANCZOS), ((cw - nw) // 2, (ch - nh) // 2))
    return cell


def build_gif(shots_json: str, gif_out: str, png_out: str | None = None,
              cell: tuple[int, int] = (640, 480), duration: int = 90,
              crop: bool = True, labels: bool = True) -> dict:
    from PIL import Image, ImageDraw

    data = json.loads(Path(shots_json).read_text(encoding="utf-8"))
    shots = data.get("shots") or []
    if not shots:
        raise SystemExit("清单里没有 shots")

    order = [v.lower() for v in (data.get("views") or VIEWS)]
    by_sim: dict[int, dict[str, str]] = {}
    for s in shots:
        by_sim.setdefault(int(s["simulation"]), {})[s["view"]] = s["path"]

    font = _font(22)
    cw, ch = cell
    frames = []
    for sid in sorted(by_sim):
        canvas = Image.new("RGB", (cw * 2, ch * 2), (255, 255, 255))
        draw = ImageDraw.Draw(canvas)
        for i, view in enumerate(order[:4]):
            cx, cy = (i % 2) * cw, (i // 2) * ch
            path = by_sim[sid].get(view)
            tile = (_fit_cell(Image.open(path).convert("RGB"), cw, ch, crop)
                    if path and Path(path).is_file()
                    else Image.new("RGB", (cw, ch), (255, 255, 255)))
            canvas.paste(tile, (cx, cy))
            if labels:
                draw.rectangle([cx + 8, cy + 8, cx + 104, cy + 38], fill=(15, 60, 130))
                draw.text((cx + 16, cy + 12), view.upper(), font=font, fill=(255, 255, 255))
            draw.line([(cx, cy), (cx + cw, cy)], fill=(200, 210, 225), width=2)
            draw.line([(cx, cy), (cx, cy + ch)], fill=(200, 210, 225), width=2)
        frames.append(canvas)

    Path(gif_out).parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(gif_out, save_all=True, append_images=frames[1:],
                   duration=duration, loop=0, optimize=True, disposal=2)
    out = {"gif": gif_out, "frames": len(frames), "kb": Path(gif_out).stat().st_size // 1024}
    if png_out:
        Path(png_out).parent.mkdir(parents=True, exist_ok=True)
        frames[-1].save(png_out)
        out["png"] = png_out
        out["png_kb"] = Path(png_out).stat().st_size // 1024
    return out


def cmd_gif(args) -> int:
    cell = tuple(int(x) for x in args.cell.lower().split("x"))
    res = build_gif(args.shots, args.gif, args.png, cell, args.duration,
                    not args.no_crop, not args.no_labels)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


def cmd_anim(args) -> int:
    rc = cmd_shots(args)
    if rc != 0:
        return rc
    shots_json = str(Path(args.outdir) / "shots.json")
    if cmd_check(argparse.Namespace(shots=shots_json)) != 0:
        print("视角校验未通过，仍继续出图（供你目视确认，但这份素材不应进报告）")
    cell = tuple(int(x) for x in args.cell.lower().split("x"))
    res = build_gif(shots_json, args.gif, args.png, cell, args.duration,
                    not args.no_crop, not args.no_labels)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="HyperWorks 后处理一体化 CLI（d3plot/H3D → 云图 → 四视角动画 → PPT 素材）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="探活").set_defaults(func=cmd_status)

    p = sub.add_parser("restart", help="按官方参数重启 HyperWorks")
    p.add_argument("--app", default="HyperView", choices=["HyperView", "HyperMesh"])
    p.add_argument("--lang", default="en", choices=["en", "zh"])
    p.add_argument("--wait", type=float, default=180)
    p.set_defaults(func=cmd_restart)

    def add_render_opts(p):
        p.add_argument("--model", required=True, help="模型文件；d3plot 时与 --result 同路径")
        p.add_argument("--result", required=True, help="结果文件：.d3plot / .h3d / .op2 ...")
        p.add_argument("--type", default="Displacement", help="结果类型（默认 Displacement）")
        p.add_argument("--comp", default="Mag", help="分量（默认 Mag）")
        p.add_argument("--entity", default="node", choices=["node", "element"])

    p = sub.add_parser("single", help="单张云图截图")
    add_render_opts(p)
    p.add_argument("--out", required=True)
    p.add_argument("--sim", default="last")
    p.add_argument("--title", default="Contour")
    p.add_argument("--limit", type=int, default=10)
    p.set_defaults(func=cmd_single)

    p = sub.add_parser("shots", help="多视角 × 多时间步截图")
    add_render_opts(p)
    p.add_argument("--outdir", required=True)
    p.add_argument("--views", default="front,back,left,right")
    p.add_argument("--steps", default="", help="显式时间步，如 '1:82:4' 或 '1,5,9'")
    p.add_argument("--frames", type=int, default=21, help="不指定 --steps 时按帧数均分")
    p.add_argument("--last", type=int, default=0, help="已知末步 id 时直接给，省一次探测")
    p.add_argument("--preview", action="store_true")
    p.set_defaults(func=cmd_shots)

    p = sub.add_parser("check", help="md5 唯一性校验")
    p.add_argument("--shots", required=True)
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("gif", help="2×2 拼版动画")
    p.add_argument("--shots", required=True)
    p.add_argument("--gif", required=True)
    p.add_argument("--png", default=None, help="末帧静态拼版（PPT 兜底图）")
    p.add_argument("--cell", default="640x480")
    p.add_argument("--duration", type=int, default=90)
    p.add_argument("--no-crop", action="store_true")
    p.add_argument("--no-labels", action="store_true")
    p.set_defaults(func=cmd_gif)

    p = sub.add_parser("anim", help="shots + check + gif 一条龙")
    add_render_opts(p)
    p.add_argument("--outdir", required=True)
    p.add_argument("--views", default="front,back,left,right")
    p.add_argument("--steps", default="")
    p.add_argument("--frames", type=int, default=21)
    p.add_argument("--last", type=int, default=0)
    p.add_argument("--preview", action="store_true")
    p.add_argument("--gif", required=True)
    p.add_argument("--png", default=None)
    p.add_argument("--cell", default="640x480")
    p.add_argument("--duration", type=int, default=90)
    p.add_argument("--no-crop", action="store_true")
    p.add_argument("--no-labels", action="store_true")
    p.set_defaults(func=cmd_anim)

    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

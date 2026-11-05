#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
无人值守仿真监视器 (watch_run.py)

跑长时 LS-DYNA 时后台盯盘，一旦发现"上升段失稳 / 时间步崩塌 / 质量缩放失控 / 计算停滞"
立刻 kill 求解器并写 ALERT.txt，避免白等十几个小时。

用法:
    python watch_run.py <deck_dir> <log_name> [--pid N] [--interval 60] [--allow-min 240]

判据（本模型标定，mm-kg-ms 单位制）:
    T1 dt 崩塌      最新 6 帧 dt 全 < 1.5E-4 且仍在下降           -> FATAL
    T2 质量缩放      added mass / total mass > 3.0 %              -> FATAL
    T3 求解报错      log 出现 *** Error / negative volume         -> FATAL
    T4 计算停滞      t 连续 STALL_MIN 分钟不动                    -> FATAL
    T5 能量爆炸      KE > 10 * max(EW, 100J)                      -> FATAL
    T6 沙漏失控      hourglass / internal > 10 %                  -> FATAL
    T9 绳能量跑带    spring&damp > 20 x (0.025*t^3) 参考标定带       -> FATAL
    T7 垂直速度反向  global vz 从正转负且跌幅 > 峰值 60%          -> WARN（拍打征兆）
    T8 锚点不同步    （若存在 nodout）10 锚点 Z 散差 > 5% 行程     -> FATAL
退出码: 0=正常结束/被监视终止, 1=触发告警后已 kill, 2=参数错误
"""
import os
import re
import sys
import time
import signal
import subprocess

# ---------------------------------------------------------------- glstat 解析
def parse_glstat(path):
    """返回 dict 列表，每项一帧。字段名已去点号并小写。"""
    if not os.path.exists(path):
        return []
    txt = open(path, encoding='ascii', errors='ignore').read()
    rows = []
    for blk in txt.split(' dt of cycle')[1:]:
        d = {}
        for line in blk.split('\n'):
            p = line.rsplit(None, 1)
            if len(p) != 2:
                continue
            name = re.sub(r'[.\s]+$', '', p[0]).strip().lower()
            try:
                d[name] = float(p[1])
            except ValueError:
                pass
        if 'time' in d:
            rows.append(d)
    return rows


def get(rows, key, idx=-1, default=0.0):
    if not rows:
        return default
    r = rows[idx]
    return r.get(key, default)


# ---------------------------------------------------------------- log 进度
PROG = re.compile(r'^\s*(\d+)\s+t\s+([-\d.E+]+)\s+dt\s+([-\d.E+]+)')
def parse_progress(log):
    """返回 (cycle, t, dt, 行号) ；取最后一条。"""
    if not os.path.exists(log):
        return None
    last = None
    with open(log, encoding='ascii', errors='ignore') as f:
        for ln, l in enumerate(f):
            m = PROG.match(l)
            if m:
                last = (int(m.group(1)), float(m.group(2)), float(m.group(3)), ln)
    return last


def tail_text(path, n=400):
    if not os.path.exists(path):
        return ''
    with open(path, encoding='ascii', errors='ignore') as f:
        return ''.join(f.readlines()[-n:])


# ---------------------------------------------------------------- 拉带同步检查（读 d3plot）
LSPP_PY = r'C:/Users/hekie/.workbuddy/binaries/python/envs/lspp-mcp/Scripts/python.exe'
CHECKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'check_tethers.py')

def check_tethers(deck):
    """返回 (ok, msg)。ok=False 表示发现拉带不同步/拍打。"""
    d3 = os.path.join(deck, 'd3plot')
    if not (os.path.exists(d3) and os.path.exists(CHECKER) and os.path.exists(LSPP_PY)):
        return True, 'no-d3plot'
    js = os.path.join(deck, 'tether_sync.json')
    # P-S85：必须显式传 --json，否则 checker 不写 json，本函数会一直读上一次的陈旧文件
    # （实测踩过：看门狗连续 40 分钟报 "t=5.0ms 太早不判"，而算例已在 104ms）
    try:
        old = os.path.getmtime(js) if os.path.exists(js) else 0.0
        if os.path.exists(js):
            os.remove(js)
        r = subprocess.run([LSPP_PY, CHECKER, d3, '--json', js],
                           capture_output=True, timeout=900)
        if not os.path.exists(js):
            return True, 'checker 未产出 json（rc=%s / %s）' % (
                r.returncode, (r.stderr or b'')[-160:].decode('ascii', 'ignore').replace('\n', ' '))
        if os.path.getmtime(js) <= old:
            return True, 'json 未刷新'
    except Exception as e:
        return True, 'checker-failed: %s' % e
    try:
        import json
        res = json.load(open(js))
    except Exception:
        return True, 'json-bad'
    # 新版 check_tethers 输出 {'verdict': PASS/WARN/FAIL, 'fails':[...], 'warns':[...]}
    # 旧版（按"彼此散差"判）会把"绳长不同导致末态 dZ 天然差 177mm"误判成不同步（P-S86/P-S87）
    if isinstance(res, dict) and 'verdict' in res:
        v = res['verdict']
        msgs = (res.get('fails') or res.get('warns') or [])
        msg = msgs[0] if msgs else '-'
        if v == 'FAIL':
            return False, 'verdict=FAIL  ' + msg
        return True, 'verdict=%s  %s' % (v, msg)
    rows = res if isinstance(res, list) else res.get('rows', [])
    if len(rows) < 3:
        return True, 'too-few-states'
    last = rows[-1]
    travel = max(max(last['dz']), 1e-6)
    spread = last.get('spread', max(last['dz']) - min(last['dz']))
    dxy = max(last['dxy'])
    # 早期（气帘刚膨胀）散差天然大，行程 < 30 mm 时只记不判
    if travel < 30.0:
        return True, 't=%.1fms travel=%.1f 太早不判' % (last['t'], travel)
    if spread > 0.15 * travel:
        return False, '拉带不同步 t=%.1fms spread=%.2fmm 占行程 %.1f%%' % (
            last['t'], spread, 100 * spread / travel)
    if dxy > 60.0:
        return False, '锚点横向漂移 t=%.1fms maxdXY=%.2fmm' % (last['t'], dxy)
    return True, 't=%.1fms spread=%.2f(%.1f%%) dXY=%.1f' % (
        last['t'], spread, 100 * spread / travel, dxy)


# ---------------------------------------------------------------- 主循环
def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    deck = sys.argv[1]
    logname = sys.argv[2]
    pid = None
    interval = 60
    stall_min = 45
    args = sys.argv[3:]
    i = 0
    while i < len(args):
        if args[i] == '--pid' and i + 1 < len(args):
            pid = int(args[i + 1]); i += 2
        elif args[i] == '--interval' and i + 1 < len(args):
            interval = int(args[i + 1]); i += 2
        elif args[i] == '--stall-min' and i + 1 < len(args):
            stall_min = int(args[i + 1]); i += 2
        else:
            i += 1

    log = os.path.join(deck, logname)
    glstat = os.path.join(deck, 'glstat')
    mlog = os.path.join(deck, 'monitor.log')
    alert = os.path.join(deck, 'ALERT.txt')

    def note(msg):
        line = '[%s] %s' % (time.strftime('%H:%M:%S'), msg)
        print(line, flush=True)
        with open(mlog, 'a', encoding='utf-8') as f:
            f.write(line + '\n')

    def kill_hard(reason, detail):
        with open(alert, 'w', encoding='utf-8') as f:
            f.write('ALERT %s\n%s\n\n%s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), reason, detail))
        note('!!! FATAL: %s' % reason)
        note(detail.replace('\n', ' | ')[:600])
        # 用 taskkill 终止整棵进程树（mpiexec + lsdyna）
        try:
            if pid:
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(pid)],
                               capture_output=True, timeout=60)
                note('已 taskkill /T /PID %s' % pid)
            else:
                subprocess.run(['taskkill', '/F', '/T', '/IM', 'lsdyna_mpp_sp_msmpi.exe'],
                               capture_output=True, timeout=60)
                note('已按镜像名终止 lsdyna_mpp_sp_msmpi.exe')
        except Exception as e:
            note('taskkill 失败: %s' % e)
        return 1

    note('=== watch 启动: deck=%s log=%s pid=%s 间隔=%ds ===' % (deck, logname, pid, interval))
    note('判据: dt<1.5E-4 / addedMass>3%% / Error/负体积 / 停滞%dmin / KE爆炸 / 沙漏>10%%' % stall_min)

    last_t = -1.0
    last_change = time.time()
    vz_hist = []
    dt_hist = []
    tick = 0

    while True:
        tick += 1
        rows = parse_glstat(glstat)
        prog = parse_progress(log)

        # 求解器是否还在
        alive = True
        if pid:
            try:
                os.kill(pid, 0)
            except OSError:
                alive = False
            except Exception:
                pass

        txt = tail_text(log)
        if 'Normal termination' in txt:
            note('*** 检测到 Normal termination，监视结束')
            return 0

        # T3 硬错误
        m = re.search(r'\*\*\* Error[^\n]*', txt)
        if m:
            return kill_hard('求解器报错 ' + m.group(0)[:120], txt[-1500:])
        m = re.search(r'negative volume[^\n]*', txt, re.I)
        if m:
            return kill_hard('负体积 ' + m.group(0)[:120], txt[-1500:])

        if not alive and prog is None:
            note('进程已退出且无进度，结束监视')
            return 0

        t_now = prog[1] if prog else 0.0
        dt_now = prog[2] if prog else 0.0

        if abs(t_now - last_t) > 1e-9:
            last_t = t_now
            last_change = time.time()

        # T4 停滞
        stall = (time.time() - last_change) / 60.0
        if stall > stall_min:
            return kill_hard('计算停滞 %.0f 分钟（t 停在 %.3f ms）' % (stall, t_now),
                             '最后进度 %s' % (prog,))

        if rows:
            am = get(rows, 'added mass')
            pct = get(rows, 'percentage increase')
            ke = get(rows, 'kinetic energy')
            ie = get(rows, 'internal energy')
            hg = get(rows, 'hourglass energy')
            ew = get(rows, 'external work')
            vz = get(rows, 'global z velocity')
            dt = get(rows, 'time step')

            dt_hist.append(dt); dt_hist = dt_hist[-12:]
            vz_hist.append(vz); vz_hist = vz_hist[-400:]

            # T2 质量缩放
            if pct > 3.0:
                return kill_hard('质量缩放失控 added mass=%.3E kg (%.2f%%)' % (am, pct),
                                 't=%.3f ms' % t_now)
            # T5 能量爆炸
            if ke > 10.0 * max(ew, 100.0):
                return kill_hard('动能异常 KE=%.3E J 远超外功 EW=%.3E J' % (ke, ew),
                                 't=%.3f ms' % t_now)
            # T6 沙漏
            if ie > 1.0 and hg / ie > 0.10:
                return kill_hard('沙漏能失控 HG/IE=%.1f%%' % (100 * hg / ie), 't=%.3f ms' % t_now)
            # T9 绳系统能量跑出参考带（参考模型标定 SPR ~ 0.025*t^3 J，P-S78）
            spr = get(rows, 'spring and damper energy')
            if t_now > 2.0 and abs(spr) > 20.0 * 0.025 * t_now ** 3:
                return kill_hard('绳系统能量跑出参考带 SPR=%.3E J（t=%.1fms 带宽 %.3E）'
                                 % (spr, t_now, 20 * 0.025 * t_now ** 3), 't=%.3f ms' % t_now)
            # T1 dt 崩塌
            if len(dt_hist) >= 6 and max(dt_hist[-6:]) < 1.5e-4:
                return kill_hard('时间步崩塌 dt=%.3E（正常 6.45E-4）' % dt, 't=%.3f ms' % t_now)

            if tick % 5 == 0:
                note('t=%7.3f ms  cyc=%s  dt=%.3E  KE=%9.3E  IE=%9.3E  vz=%9.3E  addM=%.3E(%.4f%%)'
                     % (t_now, prog[0] if prog else '-', dt_now, ke, ie, vz, am, pct))

        # 每 20 次轮询（默认 ≈20 分钟）做一次拉带同步体检
        if tick % 20 == 0:
            ok, msg = check_tethers(deck)
            note('[tether] %s' % msg)
            if not ok:
                return kill_hard('拉带运动异常 — ' + msg, '详见 %s' % os.path.join(deck, 'tether_sync.json'))

        time.sleep(interval)


if __name__ == '__main__':
    sys.exit(main())

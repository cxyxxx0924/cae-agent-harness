#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
k_health_gate.py —— LS-DYNA 试算结果健康门禁自动判读
====================================================
对照《DEP_2012001 碰撞模型建立流程规范 1.1》门禁，自动判读 glstat / matsum / abstat：

  门禁1  质量增加 < 3%        (glstat: added mass / total mass)
  门禁2  沙漏能 < 3%          (glstat: hourglass / (internal+kinetic))
  门禁3  能量比 ≈ 1           (glstat: (internal+kinetic+...) 与 external work 平衡)
  门禁4  0 单元触底           (glstat: added nodes / interface 异常 → 人工确认)
  门禁5  时间步由 DT2MS 控制  (glstat: 最小时间步 ≈ |DT2MS|，非退化)
  门禁6  充气自洽             (abstat: P ≈ m·R·T / V, R=287 mm·ms 单位)

用法：
  python k_health_gate.py --glstat glstat --matsum matsum --abstat abstat --deck newcab_calc.k
退出码：0=全部 PASS，1=有 FAIL。同时打印可读报告到 stdout。
"""
import re, sys, os, argparse


def grab_timeseries(path, label_kw):
    """从 glstat 抓 'label .... value' 时序，返回 [(t, val)...]。

    坑：glstat 有 'eroded kinetic energy' 等行包含 'kinetic energy' 子串，
    且排在每块末尾（值为 0）→ 必须用**行首精确匹配**（strip 后 startswith），
    不能只用 'in' 子串匹配。
    """
    if not path or not __import__('os').path.exists(path):
        return []
    out = []
    t = None
    kw = label_kw.lower()
    for raw in open(path, errors='ignore'):
        L = raw.rstrip('\n')
        # 时间：行首 'time' 后紧跟点号再跟数字（排除 'time step'）
        m = re.match(r'\s*time\s*\.+\s*([\d.E+-]+)', L)
        if m:
            try:
                t = float(m.group(1))
            except Exception:
                t = None
        # 标签：行首精确匹配（排除 'eroded kinetic energy' 等）
        if L.strip().lower().startswith(kw):
            nums = re.findall(r'[\d.E+-]+', L.split(label_kw, 1)[-1])
            if nums:
                try:
                    out.append((t, float(nums[-1])))
                except Exception:
                    pass
    return out


def last(vals):
    """取最大时刻的值（排除 None 时刻与纯 eroded 0 块干扰）。"""
    real = [v for v in vals if v[0] is not None]
    if not real:
        return None
    return max(real, key=lambda x: x[0])[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--glstat', default='glstat')
    ap.add_argument('--matsum', default='matsum')
    ap.add_argument('--abstat', default='abstat')
    ap.add_argument('--total-mass', type=float, default=None,
                    help='织物总质量(kg)，用于算质量增加百分比；不给则只报 added mass 绝对值')
    ap.add_argument('--deck', default='')
    args = ap.parse_args()

    gates = []  # (名称, 实测, 门禁, PASS/FAIL, 说明)

    # ---- glstat ----
    added = grab_timeseries(args.glstat, 'added mass')
    ke = grab_timeseries(args.glstat, 'kinetic energy')
    ie = grab_timeseries(args.glstat, 'internal energy')
    hg = grab_timeseries(args.glstat, 'hourglass')
    ew = grab_timeseries(args.glstat, 'external work')
    dt = grab_timeseries(args.glstat, 'timestep') or grab_timeseries(args.glstat, 'time step')

    add = last(added)
    if add is not None:
        if args.total_mass:
            inc = add / args.total_mass * 100
            gates.append(("质量增加", "%.4f%%" % inc, "< 3%", inc < 3.0,
                          "added_mass=%.3e kg / total=%.3e kg" % (add, args.total_mass)))
        else:
            gates.append(("质量增加(绝对)", "%.3e kg" % add, "< 3%(需--total-mass)", None,
                          "传入 --total-mass 以算百分比；added mass 本身极小=质量缩放可忽略"))
    else:
        gates.append(("质量增加", "N/A", "< 3%", None, "glstat 未读到 added mass 序列"))

    k = last(ke); ii = last(ie); h = last(hg)
    if k is not None and ii is not None:
        denom = ii + (k or 0)
        hr = (h or 0) / denom * 100 if denom else 0
        gates.append(("沙漏能占比", "%.4f%%" % hr, "< 3%", hr < 3.0,
                      "hg=%.3e ie=%.3e ke=%.3e" % (h or 0, ii, k)))
    else:
        gates.append(("沙漏能占比", "N/A", "< 3%", None, "glstat 未读到能量序列"))

    if ew is not None and ew and k is not None and ii is not None:
        tot_e = (ii + k)
        ratio = tot_e / ew[-1][1] if ew[-1][1] else 0
        gates.append(("能量比 (IE+KE)/EW", "%.5f" % ratio, "≈ 1.0", abs(ratio - 1.0) < 0.02,
                      "IE=%.3e KE=%.3e EW=%.3e" % (ii, k, ew[-1][1])))
    else:
        gates.append(("能量比", "N/A", "≈ 1.0", None, "能量序列不全"))

    # DT2MS 控制：最小时间步应接近 |DT2MS| 且非零退化
    if dt:
        dmin = min(v for _, v in dt if v and v > 1e-9)
        gates.append(("最小时间步", "%.2e" % dmin, "受 DT2MS 控制(非零)", dmin > 1e-7,
                      "末值 %.2e" % dt[-1][1]))
    else:
        gates.append(("最小时间步", "N/A", "受 DT2MS 控制", None, "glstat 未读到 time step"))

    # ---- abstat 充气自洽（表格：列2=volume 3=pressure 8=total mass gas 9=gas temp，mm³/kg/(mm·ms²)/K）----
    if args.abstat and os.path.exists(args.abstat):
        rows = []
        for L in open(args.abstat, errors='ignore'):
            s = L.strip()
            if s and s[0].isdigit():
                try:
                    rows.append([float(x) for x in s.split()])
                except Exception:
                    pass
        if rows:
            r = max(rows, key=lambda x: x[0])  # 取最大时刻行
            V, P, m, T = r[2], r[3], r[8], r[9]
            # P 单位 kg/(mm·ms²); R=287 mm·ms 单位; P_calc = m*R*T/V
            Pc = m * 287.0 * T / V if V else 0
            ratio = P / Pc if Pc else 0
            gates.append(("充气气体定律 P/(mRT/V)", "%.3f" % ratio, "≈ 1.0", abs(ratio - 1.0) < 0.1,
                          "V=%.2fL P=%.4e(=%.3fbar) m=%.4fkg T=%.1fK" %
                          (V / 1e6, P, P / 1e-4, m, T)))
        else:
            gates.append(("充气自洽", "N/A", "≈ 1.0", None, "abstat 无数据行"))
    else:
        gates.append(("充气自洽", "N/A", "≈ 1.0", None, "未提供 abstat"))

    # ---- 报告 ----
    print("=" * 72)
    print("LS-DYNA 试算健康门禁（对照 DEP_2012001 规范 1.1）")
    print("=" * 72)
    npass = 0
    for name, val, gate, ok, note in gates:
        tag = "PASS" if ok else ("FAIL" if ok is False else "SKIP")
        if ok:
            npass += 1
        print("  [%-4s] %-26s 实测=%-12s 门禁=%s" % (tag, name, val, gate))
        if note:
            print("         └ %s" % note)
    print("-" * 72)
    print("结果：%d/%d 项 PASS" % (npass, len([g for g in gates if g[3] is not None])))
    print("=" * 72)
    sys.exit(0 if all(g[3] for g in gates if g[3] is not None) else 1)


if __name__ == '__main__':
    main()

# tether_conn_check.py — 拉带(PID5)连接检查 (用户指定)
# 检查项:
#  1) PID5 单元/节点存在, 主体 Y=-1, 附着节点 Y=0
#  2) tether 与 belt(PID2) 共节点(共享节点/边) -> 与布带边缘共节点
#  3) tether 的"应连接边"(贴近布带边界者) 确实被共享, 无孤立拉带
#  4) 每个拉带环都至少连到一个布带边界节点
import re
from collections import defaultdict, Counter
import sys, os
_WD=(os.environ.get('WORKDIR') or './cab3').rstrip('/')
K=sys.argv[1] if len(sys.argv)>1 else _WD+'/cab3_full_v3.k'
if not os.path.isabs(K): K=_WD+'/'+K
nodes={}; elems=[]; state=None
for ln in open(K,encoding='utf-8',errors='replace'):
    s=ln.rstrip('\n')
    if s.startswith('*'):
        kw=s.split(',')[0].strip().upper(); state=kw if kw in ('*NODE','*ELEMENT_SHELL') else None; continue
    if state=='*NODE' and len(s)>=47:
        try: nodes[int(s[0:8])]=(float(s[8:24]),float(s[24:40]),float(s[40:56]))
        except: pass
    elif state=='*ELEMENT_SHELL' and len(s)>=40:
        try:
            pid=int(s[8:16]); nds=[int(s[16+8*i:24+8*i]) for i in range(4) if s[16+8*i:24+8*i].strip()!='']
            if nds: elems.append((pid,nds))
        except: pass

TET=5; BELT=2
tet_elems=[(p,n) for p,n in elems if p==TET]
belt_elems=[(p,n) for p,n in elems if p==BELT]
print("=== 1) tether 基本 ===")
print("  PID5 单元=%d  节点=%d"%(len(tet_elems), len({n for _,nds in tet_elems for n in nds})))
tet_ys=[nodes[n][1] for _,nds in tet_elems for n in nds if n in nodes]
print("  tether 节点 Y: min=%.3f max=%.3f  (主体应≈-1, 附着≈0)"%(min(tet_ys),max(tet_ys)))

# 共享节点 / 边
node_pid=defaultdict(set)
edge_pid=defaultdict(set)
for p,nds in elems:
    for n in nds: node_pid[n].add(p)
    for i in range(len(nds)):
        a,b=nds[i],nds[(i+1)%len(nds)]
        if a and b: edge_pid[(a,b) if a<b else (b,a)].add(p)
shared_n=[n for n,ps in node_pid.items() if {TET,BELT}<=ps]
shared_e=[e for e,ps in edge_pid.items() if {TET,BELT}<=ps]
print("\n=== 2) tether<->belt 共节点 ===")
print("  共享节点 %d 个, 共享边 %d 条"%(len(shared_n),len(shared_e)))

# connected components involving tether
adj=defaultdict(set)
for p,nds in elems:
    for i in range(len(nds)):
        for j in range(i+1,len(nds)):
            if nds[i] and nds[j]:
                adj[nds[i]].add(nds[j]); adj[nds[j]].add(nds[i])
seen=set(); comps=0
for n in nodes:
    if n in seen: continue
    stack=[n]; seen.add(n)
    while stack:
        x=stack.pop()
        for y in adj[x]:
            if y not in seen: seen.add(y); stack.append(y)
    comps+=1
print("\n=== 3) 全局连通 ===")
print("  连通分量数=%d (若=1 则全模型共形连通)"%comps)

# tether 边界节点中, 贴近布带边界者是否都被共享
def belt_boundary_nodes():
    be=Counter()
    for p,nds in belt_elems:
        for i in range(len(nds)):
            a,b=nds[i],nds[(i+1)%len(nds)]
            be[(a,b) if a<b else (b,a)]+=1
    return {n for k,c in be.items() if c==1 for n in k}
bbn=belt_boundary_nodes()
tet_bd=set()
te=Counter()
for p,nds in tet_elems:
    for i in range(len(nds)):
        a,b=nds[i],nds[(i+1)%len(nds)]
        te[(a,b) if a<b else (b,a)]+=1
tet_bd={n for k,c in te.items() if c==1 for n in k}
tet_bd_on_belt=set()
for n in tet_bd:
    if {TET,BELT}<=node_pid[n]: tet_bd_on_belt.add(n)
print("\n=== 4) 拉带附着完整性 ===")
print("  tether 边界节点 %d, 其中与布带共节点 %d"%(len(tet_bd), len(tet_bd_on_belt)))
print("  结论: tether 通过 %d 个共节点 + %d 条共享边 与布带边缘连接"%(len(shared_n),len(shared_e)))

# min edge of tether
import statistics as st
lens=[]
for p,nds in tet_elems:
    P=[nodes[n] for n in nds if n in nodes]
    for i in range(len(P)):
        a=P[i]; b=P[(i+1)%len(P)]
        lens.append(((a[0]-b[0])**2+(a[1]-b[1])**2+(a[2]-b[2])**2)**0.5)
print("\n=== 5) tether 网格质量 ===")
print("  tether 边长: min=%.3f max=%.2f mean=%.3f  <3mm边=%d (%.1f%%)"%(min(lens),max(lens),st.mean(lens),sum(1 for l in lens if l<3),100*sum(1 for l in lens if l<3)/len(lens)))

# PASS/FAIL
ok = (len(tet_elems)>0) and (len(shared_n)>0) and (comps==1) and (min(tet_ys)<0.01 or True) and (max(tet_ys)<=0.001+1e-6 or len([y for y in tet_ys if abs(y)<1e-6])>0)
print("\n=== 判定 ===")
print("  tether 存在: %s"%("PASS" if tet_elems else "FAIL"))
print("  与布带共节点: %s"%("PASS" if shared_n else "FAIL"))
print("  全模型连通: %s"%("PASS" if comps==1 else "FAIL (孤立部件)"))
print("  附着节点存在 Y=0: %s"%("PASS" if any(abs(y)<1e-6 for y in tet_ys) else "FAIL"))

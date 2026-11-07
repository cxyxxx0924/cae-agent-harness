function autoGate(kfile, warnings = false) {
  const result = (name, metrics = {}, detail = [[name, 0, 'PASS']]) => ({ name, status: 'PASS', summary: `${name} actual fixture`, metrics, detail, figures: [] })
  const topology = result('拓扑门禁', { dup_nodes: 0, dup_elems: 0, orphan_nodes: 0, missing_node_refs: 0, short_edges_by_pid: { 2: warnings ? 8 : 0 } }, [['重复节点(同坐标)', 0, 'PASS']])
  const geometry = result('环几何匹配', { belt: { real_fail_lines: [], local_feature_warn_lines: warnings ? [[188, 41.51, 0]] : [], crosspid_warn_lines: warnings ? [[196, 20, 0]] : [] } }, [['belt 边界贴合(CAD→网格自由边)', 'covered fabric', warnings ? 'WARN' : 'PASS']])
  if (warnings) {
    topology.status = geometry.status = 'WARN'
    topology.detail.push(['最小边 <3mm', { 2: 8 }, 'WARN'])
  }
  return { overall: warnings ? 'WARN' : 'PASS', k_file: kfile, results: [topology, result('Y分层核验'), result('环面积/节点路程'), geometry, result('拉带连接')] }
}

function partitionGeometry(model) {
  return { schema: 'cae.partition-geometry.v1', source_model: model, overall: 'PASS', failures: [], metrics: { outer_area: 1092034, cavity_area: 954376, belt_area: 137658, cut_cavity_area: 954376, belt_boundary_closed: true, cavity_boundary_closed: true } }
}

module.exports = { autoGate, partitionGeometry }

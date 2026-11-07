const autoGateNames = ['拓扑门禁', 'Y分层核验', '环面积/节点路程', '环几何匹配', '拉带连接']

function autoGatePassed(data) {
  const results = data?.results
  if (!['PASS', 'WARN'].includes(data?.overall) || !Array.isArray(results) || results.length !== autoGateNames.length) return false
  if (autoGateNames.some(name => results.filter(result => result?.name === name).length !== 1)) return false
  if (data.overall !== (results.some(result => result.status === 'WARN') ? 'WARN' : 'PASS')) return false
  return results.every(result => {
    if (!['PASS', 'WARN'].includes(result.status) || !Array.isArray(result.detail)) return false
    if (result.detail.some(row => !Array.isArray(row) || !['PASS', 'WARN', 'INFO'].includes(row[2]))) return false
    if (!result.detail.length && result.name !== '拉带连接') return false
    const warnings = result.detail.filter(row => row[2] === 'WARN')
    if ((result.status === 'WARN') !== (warnings.length > 0)) return false
    if (result.name === '拓扑门禁') {
      const metrics = result.metrics
      if (!['dup_nodes', 'dup_elems', 'orphan_nodes', 'missing_node_refs'].every(key => metrics?.[key] === 0)) return false
      const counts = Object.values(metrics.short_edges_by_pid || {})
      return counts.length > 0 && counts.every(count => Number.isInteger(count) && count >= 0) &&
        (counts.some(count => count > 0) === (result.status === 'WARN')) && warnings.every(row => /^最小边 </.test(row[0]))
    }
    if (result.name === '环几何匹配') {
      const roles = Object.values(result.metrics || {})
      return roles.length > 0 && warnings.every(row => /边界贴合\(CAD→网格自由边\)$/.test(row[0])) &&
        roles.every(role => role && Array.isArray(role.real_fail_lines) && role.real_fail_lines.length === 0 &&
          Array.isArray(role.local_feature_warn_lines) && Array.isArray(role.crosspid_warn_lines)) &&
        (roles.some(role => role.local_feature_warn_lines.length || role.crosspid_warn_lines.length) === (result.status === 'WARN'))
    }
    return result.status === 'PASS'
  })
}

function partitionGeometryPassed(data) {
  const m = data?.metrics
  if (data?.schema !== 'cae.partition-geometry.v1' || data.overall !== 'PASS' || !Array.isArray(data.failures) || data.failures.length) return false
  if (!m || ['outer_area', 'cavity_area', 'belt_area', 'cut_cavity_area'].some(key => !Number.isFinite(m[key]) || m[key] <= 0)) return false
  if (m.outer_area <= m.cavity_area) return false
  if (m.belt_boundary_closed !== true || m.cavity_boundary_closed !== true) return false
  const tolerance = Math.max(1, m.outer_area * 0.001)
  return Math.abs(m.belt_area + m.cut_cavity_area - m.outer_area) <= tolerance &&
    Math.abs(m.cut_cavity_area - m.cavity_area) <= tolerance &&
    Math.abs(m.belt_area - (m.outer_area - m.cavity_area)) <= tolerance
}

function evidencePassed(name, text) {
  if (name === 'normal_termination' || name === 'probe') return /(?:normal termination|termination time reached)/i.test(text) && !/abnormal termination|\*\*\*\s*error/i.test(text)
  if (name === 'four_views') {
    const match = text.match(/unique md5\s*:\s*(\d+)\s*\/\s*(\d+)/i)
    return Boolean(match && Number(match[1]) >= 4 && match[1] === match[2] && ['front', 'back', 'left', 'right'].every(view => new RegExp(`['"]${view}['"]\\s*:\\s*[1-9]\\d*`).test(text)))
  }
  try {
    const data = JSON.parse(text)
    if (name === 'auto_gate') return autoGatePassed(data)
    const verdicts = [data.overall, data.verdict, data.result?.verdict, data.status].filter(value => value !== undefined)
    if (verdicts.some(value => ['WARN', 'FAIL', 'FAILED', 'SKIP'].includes(value)) || data.passed === false) return false
    return verdicts.includes('PASS') || data.passed === true
  } catch {
    if (name === 'auto_gate') return false
    if (/\b(?:WARN|WARNING|FAIL|FAILED|ABNORMAL TERMINATION)\b(?!\s*[:=]\s*0\b)/i.test(text) || /\*\*\*\s*error/i.test(text) || (name === 'health' && /\bSKIP\b/.test(text))) return false
    return /\bPASS(?:ED)?\b|VERIFY_FAIL=0|\b(?:errors|failures)\s*[:=]\s*0\b/i.test(text)
  }
}

module.exports = { autoGatePassed, partitionGeometryPassed, evidencePassed }

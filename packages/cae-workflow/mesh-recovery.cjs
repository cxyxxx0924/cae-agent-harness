const fs = require('node:fs')
const path = require('node:path')
const { createHash } = require('node:crypto')

const meshOutputs = { mesh_model: 'curtain_mesh.hm', curtain_k: 'curtain_airbag.k', preview: 'mesh_preview.png' }
const sha256 = file => createHash('sha256').update(fs.readFileSync(file)).digest('hex')
const read = file => { try { return JSON.parse(fs.readFileSync(file, 'utf8')) } catch { return null } }
const samePath = (a, b) => typeof a === 'string' && typeof b === 'string' && path.resolve(a) === path.resolve(b)
const meshParameters = parameters => Object.fromEntries(Object.entries(parameters || {}).filter(([key]) => key !== 'partitioned_model').sort(([a], [b]) => a.localeCompare(b)))

function prepareMeshRecovery(state, source, parameters) {
  const directory = state.jobDirectory
  const previous = read(path.join(directory, 'mesh.parameters.json'))
  const previousRecovery = read(path.join(directory, 'mesh.recovery.json'))
  const input = path.join(directory, 'input', 'partitioned.hm')
  let reason = ''
  if (state.feedback) reason = '用户要求调整网格，需按反馈重建。'
  else if (!previous || JSON.stringify(meshParameters(previous)) !== JSON.stringify(meshParameters(parameters))) reason = '没有相同参数的执行记录，按本次参数生成网格。'
  else if (!fs.existsSync(input) || sha256(input) !== sha256(source)) reason = '分区模型已变化，不能复用原网格。'
  const artifacts = []
  for (const [role, name] of Object.entries(meshOutputs)) {
    const file = state.stages[state.current].artifacts.find(artifact => artifact.role === role && artifact.remote !== true)?.path || path.join(directory, 'out', name)
    try {
      if (fs.statSync(file).isFile() && fs.statSync(file).size > 0 && path.relative(directory, file).split(path.sep)[0] !== '..') artifacts.push({ role, path: file, sha256: sha256(file) })
    } catch {}
  }
  if (artifacts.length !== Object.keys(meshOutputs).length) reason ||= '现有网格模型、K 文件或预览不完整，需要生成缺失产物。'
  if (!reason && previousRecovery?.mode === 'rebuild') {
    const unchanged = ['mesh_model', 'curtain_k'].every(role => {
      const candidate = artifacts.find(artifact => artifact.role === role)
      return previousRecovery.artifacts?.some(artifact => artifact.role === role && samePath(artifact.path, candidate.path) && artifact.sha256 === candidate.sha256)
    })
    const completed = state.stages[state.current].artifacts.some(artifact => artifact.executionId === previousRecovery.executionId)
    if (unchanged && !completed) reason = '现有网格仍为上次重建前的产物，不能用新参数复用旧结果。'
  }
  return {
    executionId: state.executionId, mode: reason ? 'rebuild' : 'verify_existing',
    reason: reason || '先独立回读现有 HM，并针对现有 K 重跑四道门禁；验证通过后复用，失败才返工。',
    source, sourceSha256: sha256(source), parameters: meshParameters(parameters), artifacts,
  }
}

function reusableMeshArtifact(state, artifact) {
  const recovery = state.meshRecovery
  if (recovery?.mode !== 'verify_existing' || recovery.executionId !== state.executionId) return false
  const candidate = recovery.artifacts.find(file => file.role === artifact.role && samePath(file.path, artifact.path))
  try {
    return Boolean(candidate && recovery.sourceSha256 === sha256(recovery.source) &&
      JSON.stringify(recovery.parameters) === JSON.stringify(meshParameters(state.parameters.mesh)) && candidate.sha256 === sha256(artifact.path))
  } catch { return false }
}

module.exports = { prepareMeshRecovery, reusableMeshArtifact, samePath, sha256 }

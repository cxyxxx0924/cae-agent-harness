const fs = require('node:fs')
const path = require('node:path')
const { createHash, randomUUID } = require('node:crypto')
const { STAGES } = require('./fields.cjs')

const copy = value => JSON.parse(JSON.stringify(value))
const now = () => new Date().toISOString()
const localFile = value => { try { return fs.statSync(value).isFile() } catch { return false } }
const localDirectory = value => { try { return fs.statSync(value).isDirectory() } catch { return false } }
const absolute = value => path.isAbsolute(value) || path.win32.isAbsolute(value)
const required = (field, values) => field.requiredWhen ? values[field.requiredWhen[0]] === field.requiredWhen[1] : field.required
const NO_CHANGE = Symbol('no change')
const artifactExtensions = { geometry: ['.hm'], partitioned_model: ['.hm'], mesh_model: ['.hm'], curtain_k: ['.k', '.key'], combined_k: ['.k', '.key'], preview: ['.png', '.jpg', '.jpeg', '.webp'], animation: ['.gif'], report: ['.pptx'] }

function validateParameters(stage, raw) {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw new Error('请填写当前阶段的参数。')
  const values = {}, errors = []
  for (const field of stage.fields) {
    if (field.requiredWhen && !required(field, raw)) continue
    const value = typeof raw[field.id] === 'string' ? raw[field.id].trim() : raw[field.id]
    const empty = value === undefined || value === null || value === '' || (field.type === 'checkbox' && value !== true)
    if (empty) { if (required(field, raw)) errors.push(`请填写或确认“${field.label}”。`); continue }
    if (field.type === 'checkbox') { values[field.id] = value === true; continue }
    if (field.type === 'number') {
      const parsed = typeof value === 'number' || typeof value === 'string' ? Number(value) : NaN
      if (!Number.isFinite(parsed) || (field.integer && !Number.isInteger(parsed)) || (field.min !== undefined && parsed < field.min) || (field.max !== undefined && parsed > field.max)) errors.push(`“${field.label}”的数值无效。`)
      else values[field.id] = parsed
      continue
    }
    if (typeof value !== 'string' || value.includes('\0') || value.length > 32768) { errors.push(`“${field.label}”格式无效。`); continue }
    values[field.id] = value.trim()
    if (required(field, raw) && !values[field.id]) errors.push(`请填写“${field.label}”。`)
    if (field.type === 'select' && !field.choices.includes(value)) errors.push(`请选择有效的“${field.label}”。`)
    if (['file', 'directory'].includes(field.type)) {
      if (!absolute(value) || !(field.type === 'file' ? localFile(value) : localDirectory(value))) errors.push(`“${field.label}”必须是本机可访问的完整${field.type === 'file' ? '文件' : '目录'}路径。`)
      if (field.extensions && !field.extensions.includes(path.extname(value).slice(1).toLowerCase())) errors.push(`“${field.label}”的文件类型无效。`)
    }
  }
  if (stage.id === 'import' && values.workdir && /[^\x20-\x7e]/.test(values.workdir)) errors.push('HyperMesh 批处理工作目录请使用全英文路径。')
  if (stage.id === 'solve') {
    if (!/^\d+(?:\.\d+)?[mg]$/i.test(values.memory || '') || parseFloat(values.memory) <= 0) errors.push('求解器内存请填写类似 2000m 或 4g 的值。')
    if (values.probe_time > values.termination_time) errors.push('探针时长不能超过正式计算时长。')
  }
  if (stage.id === 'postprocess' && values.end_time <= values.start_time) errors.push('动画结束时刻必须晚于开始时刻。')
  if (stage.id === 'report' && values.report_mode === 'assessment' && values.detonation_time > values.measurement_time) errors.push('厚度评判时刻不能早于起爆时刻。')
  if (stage.id === 'report' && values.report_mode === 'assessment' && (values.early_time < values.detonation_time || values.early_time > values.measurement_time)) errors.push('展开对照时刻应在起爆时刻与厚度评判时刻之间。')
  if (errors.length) throw new Error(errors.join('\n'))
  if (values.head_points) {
    const points = readJson(values.head_points)
    const rows = Array.isArray(points) ? points : points?.heads || points?.rows
    if (!Array.isArray(rows) || !rows.length || rows.some(point => !point || !Number.isFinite(point.x) || !Number.isFinite(point.z))) throw new Error('头部测点 JSON 需包含非空数组（或 heads/rows 数组），每个测点必须有数值 x、z。')
  }
  return values
}

function readJson(file) {
  try { return JSON.parse(fs.readFileSync(file, 'utf8')) } catch { throw new Error(`无法读取 JSON 配置：${file}`) }
}

function missingSoftware(stage, software = {}) {
  const need = (field, label) => !software[field] || !localFile(software[field]) ? { field, message: `尚未配置可用的${label}，请到“设置 → 仿真软件”完成配置。已选文件和参数会保留。` } : null
  if (['import', 'partition', 'mesh'].includes(stage.id)) return need('hmbatch', ' HyperMesh 批处理程序')
  if (stage.id === 'postprocess') return need('hyperview', ' HyperView 程序')
  if (stage.id === 'solve') {
    if (!['local', 'server'].includes(software.solverLocation) || !['software', 'service'].includes(software.localSolverType)) return { field: 'lsdyna', message: '请到“设置 → 仿真软件”选择求解位置和接入方式。' }
    const field = software.solverLocation === 'server' ? 'solverServerUrl' : software.localSolverType === 'service' ? 'solverLocalServiceUrl' : null
    if (!field) return need('lsdyna', ' LS-DYNA 求解器')
    try {
      const value = software[field], endpoint = new URL(value)
      if (!/^https?:\/\//i.test(value) || /\s/.test(value) || endpoint.username || endpoint.password || endpoint.search || endpoint.hash) throw new Error()
      return null
    } catch { return { field, message: '尚未配置有效的求解服务地址，请到“设置 → 仿真软件”完成配置。已选文件和参数会保留。' } }
  }
  return null
}

function appendTrace(state, text, kind = 'info') {
  state.traces.push({ time: now(), text, kind })
  state.traces = state.traces.slice(-100)
}

class WorkflowStore {
  constructor(directory) { this.directory = directory }
  file(sessionId) {
    if (typeof sessionId !== 'string' || !sessionId || sessionId.length > 512) throw new Error('会话标识无效。')
    return path.join(this.directory, createHash('sha256').update(sessionId).digest('hex') + '.json')
  }
  load(sessionId) {
    const file = this.file(sessionId)
    if (!fs.existsSync(file)) return null
    const state = readJson(file)
    if (state.version !== 1 || state.sessionId !== sessionId || !STAGES[state.current]) throw new Error('工作流记录格式无效，请保留记录并联系维护人员。')
    return state
  }
  change(sessionId, revision, change) {
    fs.mkdirSync(this.directory, { recursive: true })
    const file = this.file(sessionId), lock = file + '.lock'
    let descriptor
    try { descriptor = fs.openSync(lock, 'wx') } catch (error) {
      if (error.code !== 'EEXIST') throw error
      let stale = false
      try {
        const owner = JSON.parse(fs.readFileSync(lock, 'utf8'))
        try { process.kill(owner.pid, 0) } catch (error) { stale = error.code === 'ESRCH' }
      } catch { stale = fs.statSync(lock).mtimeMs < Date.now() - 10000 }
      if (!stale) throw new Error('工作流正在更新，请稍后重试。')
      fs.rmSync(lock, { force: true })
      try { descriptor = fs.openSync(lock, 'wx') } catch { throw new Error('工作流正在更新，请稍后重试。') }
    }
    try {
      fs.writeFileSync(descriptor, JSON.stringify({ pid: process.pid }))
      let state = this.load(sessionId)
      if (revision !== undefined && state?.revision !== revision) throw new Error('工作流状态已更新，请刷新参数后重试。')
      const changed = change(state)
      if (changed === NO_CHANGE) return state
      state = changed
      state.revision = (state.revision || 0) + 1
      state.updatedAt = now()
      const temporary = `${file}.${randomUUID()}.tmp`
      try { fs.writeFileSync(temporary, JSON.stringify(state), { mode: 0o600 }); fs.renameSync(temporary, file) }
      finally { fs.rmSync(temporary, { force: true }) }
      return state
    } finally { fs.closeSync(descriptor); fs.rmSync(lock, { force: true }) }
  }
  create(sessionId) {
    return this.change(sessionId, undefined, previous => {
      if (previous) return NO_CHANGE
      const state = { version: 1, id: randomUUID(), sessionId, revision: 0, current: 0, status: 'parameters', parameters: {}, stages: STAGES.map((stage, i) => ({ id: stage.id, status: i === 0 ? 'parameters' : 'pending', artifacts: [] })), traces: [], createdAt: now() }
      appendTrace(state, '气帘工作流已创建，等待几何输入和项目参数。')
      return state
    })
  }
  submit(sessionId, revision, raw, software) {
    return this.change(sessionId, revision, state => {
      if (!state || !['parameters', 'ready', 'blocked', 'error', 'interrupted'].includes(state.status)) throw new Error('当前阶段不能修改参数。')
      const stage = STAGES[state.current], values = validateParameters(stage, raw)
      if (['error', 'interrupted'].includes(state.status) && stage.id === 'solve' && raw.retry_confirmed !== true) throw new Error('请先检查本机或服务端任务状态，并确认本次可以重新提交，避免重复求解。')
      if (state.additionalRequest) {
        if (typeof raw.additional_input !== 'string' || !raw.additional_input.trim() || raw.additional_input.length > 16000) throw new Error('请填写当前阶段补充要求的参数或说明。')
        values.additional_input = raw.additional_input.trim()
      }
      if (stage.id === 'solve' && (software.solverLocation === 'server' || software.localSolverType === 'service') && !values.service_paths_confirmed) throw new Error('请先确认模型及 INCLUDE 文件能被所选求解服务访问。')
      state.parameters[stage.id] = values
      state.configuration = missingSoftware(stage, software)
      state.status = state.configuration ? 'blocked' : 'ready'
      state.stages[state.current].status = state.status
      state.error = ''
      state.configuration = state.configuration || null
      appendTrace(state, state.configuration?.message || `${stage.title}参数已由用户确认，等待执行。`, state.configuration ? 'warning' : 'success')
      return state
    })
  }
  confirm(sessionId, revision) {
    return this.change(sessionId, revision, state => {
      if (!state || state.status !== 'review') throw new Error('当前没有等待确认的结果。')
      const stage = STAGES[state.current]
      state.stages[state.current].status = 'done'
      appendTrace(state, `用户已确认${stage.title}结果。`, 'success')
      return this.advance(state)
    })
  }
  adjust(sessionId, revision, feedback) {
    if (typeof feedback !== 'string' || !feedback.trim() || feedback.length > 10000) throw new Error('请填写需要调整的内容。')
    return this.change(sessionId, revision, state => {
      if (!state || state.status !== 'review') throw new Error('当前没有可调整的结果。')
      state.feedback = feedback.trim()
      state.status = 'parameters'
      state.stages[state.current].status = 'parameters'
      appendTrace(state, `用户请求调整：${state.feedback}`)
      return state
    })
  }
  advance(state) {
    if (state.current === STAGES.length - 1) { state.status = 'completed'; return state }
    state.current += 1
    state.status = 'parameters'
    state.stages[state.current].status = 'parameters'
    state.configuration = null
    state.feedback = ''
    state.additionalRequest = ''
    appendTrace(state, `请填写或确认${STAGES[state.current].title}所需参数。`)
    return state
  }
  begin(sessionId, software, root) {
    return this.change(sessionId, undefined, state => {
      if (!state || state.status !== 'ready') throw new Error('必须先由用户在工作流表单中确认本阶段参数。')
      const stage = STAGES[state.current]
      if (state.current > 0 && state.stages[state.current - 1].status !== 'done') throw new Error('上一阶段尚未完成或尚未由用户确认。')
      const missing = missingSoftware(stage, software)
      if (missing) { state.status = 'blocked'; state.configuration = missing; appendTrace(state, missing.message, 'warning'); return state }
      const intake = state.parameters.import
      const jobDirectory = path.join(intake.workdir, `cae-${state.id}`)
      fs.mkdirSync(jobDirectory, { recursive: true })
      fs.mkdirSync(path.join(jobDirectory, 'out'), { recursive: true })
      state.jobDirectory = jobDirectory
      state.executionId = randomUUID()
      state.startedAt = now()
      state.status = 'running'
      state.stages[state.current].status = 'running'
      state.stages[state.current].attempts = (state.stages[state.current].attempts || 0) + 1
      state.skillPath = path.join(root, stage.skill, 'SKILL.md')
      if (!localFile(state.skillPath)) throw new Error(`工作流 skill 缺失：${state.skillPath}`)
      const parameters = copy(state.parameters)
      if (stage.id === 'mesh') {
        const source = state.stages[1].artifacts.find(artifact => artifact.role === 'partitioned_model')?.path
        if (!source || !localFile(source)) throw new Error('缺少已确认的分区模型。')
        fs.mkdirSync(path.join(jobDirectory, 'input'), { recursive: true })
        fs.copyFileSync(source, path.join(jobDirectory, 'input', 'partitioned.hm'))
        parameters.mesh.partitioned_model = source
        if (parameters.mesh.reference_mesh_k) parameters.mesh.reference_mesh_k = path.resolve(parameters.mesh.reference_mesh_k)
      }
      if (stage.id === 'solve') {
        const p = parameters.solve
        const curtain = state.stages[2].artifacts.find(a => a.role === 'curtain_k')?.path
        if (!curtain || !localFile(curtain)) throw new Error('缺少已确认的当前气帘 K 文件，请恢复网格产物。')
        const config = { project: intake.project_name, workdir: jobDirectory, inputs: { ref_deck: p.reference_deck, cab_k: curtain, biw_k: p.body_k, mat_k: p.material_k }, placement: { DY: p.placement_dy, DZ: p.placement_dz }, tether: { belt_count: p.tether_count }, run: { endtim: p.termination_time, probe_time: p.probe_time, ncpu: p.ncpu, memory: p.memory } }
        fs.writeFileSync(path.join(jobDirectory, 'solve.case.json'), JSON.stringify(config, null, 2))
      }
      fs.writeFileSync(path.join(jobDirectory, `${stage.id}.parameters.json`), JSON.stringify(parameters[stage.id], null, 2))
      state.toolRuns = []
      state.configuration = null
      appendTrace(state, stage.id === 'solve' ? '组合求解准备中，通常需要数小时；仅汇报真实执行状态。' : `${stage.title}已开始。`)
      return state
    })
  }
  recordTool(sessionId, executionId, name, success) {
    return this.change(sessionId, undefined, state => {
      if (state?.status !== 'running' || state.executionId !== executionId) return NO_CHANGE
      state.toolRuns.push({ name, success, time: now() })
      state.toolRuns = state.toolRuns.slice(-100)
      appendTrace(state, `${name}：${success ? '执行完成' : '执行失败'}`, success ? 'success' : 'error')
      return state
    })
  }
  complete(sessionId, executionId, artifacts) {
    return this.change(sessionId, undefined, state => {
      if (!state || state.status !== 'running' || state.executionId !== executionId) throw new Error('执行标识已失效，不能更新当前工作流。')
      const stage = STAGES[state.current]
      if (!state.toolRuns.some(run => run.success && /^(?:bash|pwsh|job_output|mcp__)/.test(run.name))) throw new Error('尚无真实工具执行记录，不能将阶段标记为完成。')
      if (!Array.isArray(artifacts) || artifacts.length > 50) throw new Error('请提供真实产物列表。')
      for (const role of stage.outputs) if (!artifacts.some(artifact => artifact.role === role)) throw new Error(`缺少阶段产物：${role}`)
      const verified = artifacts.map(artifact => {
        if (!artifact || typeof artifact.path !== 'string' || !absolute(artifact.path) || typeof artifact.role !== 'string') throw new Error('产物需提供有效的 role 和完整路径。')
        if (artifactExtensions[artifact.role] && !artifactExtensions[artifact.role].includes(path.extname(artifact.path).toLowerCase())) throw new Error(`产物文件类型与用途不符：${artifact.role}`)
        if (artifact.remote === true) {
          if (stage.id !== 'solve' || !['d3plot', 'combined_k'].includes(artifact.role) || !state.parameters.solve.service_paths_confirmed) throw new Error('仅服务端求解模型和结果允许使用远程路径。')
        } else {
          if (!localFile(artifact.path) || fs.statSync(artifact.path).size === 0) throw new Error(`产物不存在或为空：${artifact.path}`)
          if (fs.statSync(artifact.path).mtimeMs < Date.parse(state.startedAt) - 2000) throw new Error(`产物早于本次执行，请核对是否使用了旧结果：${artifact.path}`)
        }
        return { role: artifact.role, path: artifact.path, remote: artifact.remote === true, executionId: state.executionId }
      })
      const verification = artifacts.find(artifact => artifact.role === 'verification')
      if (verification) {
        const text = fs.readFileSync(verification.path, 'utf8')
        if (stage.id === 'partition') {
          if (!/\bVERIFY_FAIL=0\b/.test(text) || /\bVERIFY_FAIL=[1-9]/.test(text)) throw new Error('分区独立回读未通过 VERIFY_FAIL=0。')
        } else {
          let report
          try { report = JSON.parse(text) } catch { throw new Error('请将实际门禁记录汇总为 JSON：checks 数组逐条包含 name、passed、evidence。') }
          const checks = report.checks
          if (!Array.isArray(checks) || !checks.length || checks.some(check => check.passed !== true || !localFile(check.evidence) || fs.statSync(check.evidence).size === 0 || fs.statSync(check.evidence).mtimeMs < Date.parse(state.startedAt) - 2000)) throw new Error('门禁未全部通过或缺少本次执行的实际证据文件。')
          const names = stage.id === 'mesh' ? ['strict_k', 'auto_gate', 'quality', 'partition_coverage'] : stage.id === 'solve' ? ['parity', 'damper', 'probe', 'normal_termination', 'health'] : ['four_views']
          if (names.some(name => !checks.some(check => check.name === name))) throw new Error(`缺少必需门禁：${names.join('、')}`)
          for (const check of checks) {
            const evidence = fs.readFileSync(check.evidence, 'utf8')
            if (!evidencePassed(check.name, evidence)) throw new Error(`门禁证据没有通过：${check.name}`)
          }
        }
      }
      if (stage.id === 'solve' && !state.toolRuns.some(run => run.success && run.name === 'mcp__cae__lsdyna_solve')) throw new Error('缺少所选求解后端的真实执行记录。')
      state.stages[state.current].artifacts = verified
      state.stages[state.current].completedAt = now()
      appendTrace(state, `${stage.title}产物已验证${stage.review ? '，等待用户确认。' : '。'}`, 'success')
      state.stages[state.current].status = stage.review ? 'review' : 'done'
      if (stage.review) { state.status = 'review'; return state }
      return this.advance(state)
    })
  }
  fail(sessionId, executionId, message, status = 'error') {
    if (!['error', 'interrupted'].includes(status)) throw new Error('无效的任务状态。')
    return this.change(sessionId, undefined, state => {
      if (!state || state.status !== 'running' || state.executionId !== executionId) throw new Error('当前任务已经结束或执行标识已失效。')
      state.status = status
      state.error = String(message).slice(0, 8000)
      state.stages[state.current].status = status
      appendTrace(state, state.error, 'error')
      return state
    })
  }
  requestInput(sessionId, executionId, message) {
    if (typeof message !== 'string' || !message.trim() || message.length > 16000) throw new Error('请说明还缺少哪些项目参数。')
    return this.change(sessionId, undefined, state => {
      if (!state || state.status !== 'running' || state.executionId !== executionId) throw new Error('执行标识已失效。')
      state.additionalRequest = message.trim()
      state.status = 'parameters'
      state.stages[state.current].status = 'parameters'
      appendTrace(state, `等待补充参数：${state.additionalRequest}`, 'warning')
      return state
    })
  }
  interruptRunning() {
    if (!fs.existsSync(this.directory)) return
    for (const file of fs.readdirSync(this.directory).filter(file => /^[a-f0-9]{64}\.json$/.test(file))) {
      const state = readJson(path.join(this.directory, file))
      if (state.status === 'running') this.fail(state.sessionId, state.executionId, '后台运行已中断。请先检查软件或服务端任务状态，再决定是否重试，避免重复提交。', 'interrupted')
    }
  }
  hasRunning() {
    if (!fs.existsSync(this.directory)) return false
    return fs.readdirSync(this.directory).filter(file => /^[a-f0-9]{64}\.json$/.test(file)).some(file => readJson(path.join(this.directory, file)).status === 'running')
  }
}

function evidencePassed(name, text) {
  if (name === 'normal_termination' || name === 'probe') return /(?:normal termination|termination time reached)/i.test(text) && !/abnormal termination|\*\*\*\s*error/i.test(text)
  if (name === 'four_views') {
    const match = text.match(/unique md5\s*:\s*(\d+)\s*\/\s*(\d+)/i)
    return Boolean(match && Number(match[1]) >= 4 && match[1] === match[2] && ['front', 'back', 'left', 'right'].every(view => new RegExp(`['"]${view}['"]\\s*:\\s*[1-9]\\d*`).test(text)))
  }
  try {
    const data = JSON.parse(text)
    return data.overall === 'PASS' || data.verdict === 'PASS' || data.result?.verdict === 'PASS' || data.passed === true || data.status === 'PASS'
  } catch {
    if (/\b(?:FAIL|FAILED|ABNORMAL TERMINATION)\b(?!\s*[:=]\s*0\b)/i.test(text) || /\*\*\*\s*error/i.test(text) || (name === 'health' && /\bSKIP\b/.test(text))) return false
    return /\bPASS(?:ED)?\b|VERIFY_FAIL=0|\b(?:errors|failures)\s*[:=]\s*0\b/i.test(text)
  }
}

module.exports = { WorkflowStore, STAGES, validateParameters, missingSoftware }

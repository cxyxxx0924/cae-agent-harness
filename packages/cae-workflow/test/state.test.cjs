const assert = require('node:assert/strict')
const fs = require('node:fs')
const { tmpdir } = require('node:os')
const path = require('node:path')
const { test } = require('node:test')
const { WorkflowStore, STAGES, validateParameters, missingSoftware } = require('../state.cjs')
const { autoGate, partitionGeometry } = require('./gate-fixtures.cjs')
const { sha256 } = require('../mesh-recovery.cjs')

function fixture(t) {
  const directory = fs.mkdtempSync(path.join(tmpdir(), 'cae-workflow-'))
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }))
  const file = (name, contents = 'actual fixture') => {
    const result = path.join(directory, name)
    fs.mkdirSync(path.dirname(result), { recursive: true })
    fs.writeFileSync(result, typeof contents === 'string' ? contents : JSON.stringify(contents))
    return result
  }
  const executable = file('hmbatch.exe')
  const software = { hmbatch: executable, hyperview: executable, lsdyna: executable, solverLocation: 'local', localSolverType: 'software' }
  const intake = { project_name: 'Current project', igs_file: file('input.igs'), workdir: directory }
  const store = new WorkflowStore(path.join(directory, 'state'))
  const solve = { body_k: file('body.k'), reference_deck: file('main.key'), material_k: file('material.k'), placement_dy: 0, placement_dz: -2, tether_count: 5, termination_time: 80, probe_time: 2, ncpu: 4, memory: '2000m', hours_confirmed: true }
  const config = {
    plane: 'xy', layers: ['belt', 'cavity', 'seam', 'tether'].map((role, index) => ({ role, cid: index + 20, pid: index + 30, tag: `L${index + 1}`, z: [0] })),
    parts: ['belt', 'cavity', 'seam', 'tether'], assemble: {}, gates: { gate_case: file('gate_case.json', {}), partition_manifest: file('manifest.json', {}) },
  }
  const mesh = { element_size: 7, element_type: 'mixed', reference_mesh_k: file('reference.k') }
  const root = path.resolve(__dirname, '../../..')
  const setStage = (index, status = 'parameters') => {
    store.create('s1')
    return store.change('s1', undefined, state => { state.current = index; state.status = status; state.parameters.import = intake; state.stages.slice(0, index).forEach(stage => { stage.status = 'done' }); return state })
  }
  return { directory, file, software, intake, store, solve, mesh, config, root, setStage }
}

function outputs(f, state) {
  const stage = STAGES[state.current]
  const checks = stage.id === 'mesh' ? ['strict_k', 'auto_gate', 'quality', 'partition_coverage'] : stage.id === 'solve' ? ['parity', 'damper', 'probe', 'normal_termination', 'health'] : ['four_views']
  const extensions = { geometry: '.hm', partitioned_model: '.hm', mesh_model: '.hm', curtain_k: '.k', combined_k: '.k', d3plot: '', preview: '.png', animation: '.gif', report: '.pptx' }
  return stage.outputs.map(role => ({ role, path: f.file(`${stage.id}/${role}${extensions[role] ?? '.txt'}`, role === 'geometry_verification' ? partitionGeometry(path.join(f.directory, 'partition/partitioned_model.hm')) : role !== 'verification' ? 'actual output fixture' : stage.id === 'partition' ? 'VERIFY_FAIL=0' : { checks: checks.map(name => ({ name, passed: true, evidence: f.file(`${stage.id}/${name}.log`, name === 'auto_gate' ? autoGate(path.join(f.directory, 'mesh/curtain_k.k')) : name === 'four_views' ? "{'front': 3, 'back': 3, 'left': 3, 'right': 3}\nunique md5: 12 / 12" : ['probe', 'normal_termination'].includes(name) ? 'Normal termination' : 'PASS') })) }) }))
}

test('workflow waits for user input, retains missing-software parameters, and rejects stale submissions', t => {
  const f = fixture(t)
  let state = f.store.create('s1')
  assert.equal(f.store.create('s1').revision, state.revision)
  assert.throws(() => f.store.begin('s1', f.software, f.root), /用户/)
  state = f.store.submit('s1', state.revision, f.intake, { ...f.software, hmbatch: '' })
  assert.equal(state.status, 'blocked')
  assert.equal(state.parameters.import.igs_file, f.intake.igs_file)
  assert.equal(state.configuration.field, 'hmbatch')
  assert.throws(() => f.store.submit('s1', state.revision - 1, f.intake, f.software), /已更新/)
  state = f.store.submit('s1', state.revision, f.intake, f.software)
  assert.equal(state.status, 'ready')
  state = f.store.begin('s1', f.software, f.root)
  assert.equal(state.status, 'running')
  assert.ok(fs.existsSync(path.join(state.jobDirectory, 'import.parameters.json')))
  assert.throws(() => f.store.begin('s1', f.software, f.root), /用户/)
  assert.equal(new WorkflowStore(f.store.directory).load('s1').executionId, state.executionId)
  assert.equal(f.store.load('other-session'), null)
})

test('case-specific solver, time and assessment parameters are required and validated', t => {
  const f = fixture(t)
  const solveStage = STAGES.find(stage => stage.id === 'solve')
  for (const key of ['placement_dy', 'termination_time', 'tether_count', 'hours_confirmed']) {
    const raw = { ...f.solve }; delete raw[key]
    assert.throws(() => validateParameters(solveStage, raw), /填写或确认/)
  }
  assert.equal(validateParameters(solveStage, f.solve).placement_dy, 0)
  assert.throws(() => validateParameters(solveStage, { ...f.solve, placement_dy: ' ' }), /填写/)
  assert.throws(() => validateParameters(solveStage, { ...f.solve, tether_count: 1.5 }), /数值无效/)
  assert.throws(() => validateParameters(solveStage, { ...f.solve, memory: '0m' }), /内存/)
  assert.throws(() => validateParameters(solveStage, { ...f.solve, probe_time: 90 }), /探针/)
  const post = STAGES.find(stage => stage.id === 'postprocess')
  assert.throws(() => validateParameters(post, { local_d3plot: f.file('d3plot'), start_time: 2, end_time: 1, frames: 21, fps: 10, result_type: 'displacement' }), /结束时刻/)
  const report = STAGES.find(stage => stage.id === 'report')
  assert.doesNotThrow(() => validateParameters(report, { title: 'Report', analyst: 'Analyst', report_mode: 'summary' }))
  assert.throws(() => validateParameters(report, { title: 'Report', analyst: 'Analyst', report_mode: 'assessment' }), /头部|坐标/)
})

test('mesh form does not require case.json and accepts only an optional project reference mesh', t => {
  const f = fixture(t)
  const stage = STAGES.find(stage => stage.id === 'mesh')
  const raw = validateParameters(stage, f.mesh)
  assert.equal(raw.reference_mesh_k, f.mesh.reference_mesh_k)
  assert.equal(stage.fields.some(field => field.id === 'case_file'), false)
  assert.equal(validateParameters(stage, { element_size: 5, element_type: 'mixed' }).element_size, 5)
  assert.throws(() => validateParameters(stage, { element_size: 5, element_type: 'mixed', reference_mesh_k: 'relative.k' }), /完整文件路径/)
})

test('software validation respects the selected backend and checks executable existence', t => {
  const f = fixture(t)
  const stage = STAGES.find(stage => stage.id === 'solve')
  assert.equal(missingSoftware(STAGES[0], { hmbatch: '/missing/hmbatch.exe' }).field, 'hmbatch')
  assert.equal(missingSoftware(stage, { ...f.software, solverLocation: 'server', lsdyna: '', solverServerUrl: 'https://solver.example.com/api' }), null)
  assert.equal(missingSoftware(stage, { ...f.software, localSolverType: 'service', lsdyna: '', solverLocalServiceUrl: '' }).field, 'solverLocalServiceUrl')
  assert.ok(missingSoftware(stage, { ...f.software, solverLocation: 'server', solverServerUrl: 'https://user:secret@solver.example.com' }))
  const state = f.setStage(3)
  assert.throws(() => f.store.submit('s1', state.revision, f.solve, { ...f.software, solverLocation: 'server', solverServerUrl: 'https://solver.example.com' }), /INCLUDE/)
})

test('all six stages use submitted values and review stages require a user confirmation', t => {
  const f = fixture(t)
  let state = f.store.create('s1')
  const parameters = [f.intake, {}, f.mesh, f.solve, { local_d3plot: f.file('result/d3plot'), start_time: 0, end_time: 80, frames: 21, fps: 10, result_type: 'displacement' }, { title: 'Current report', analyst: 'Current analyst', report_mode: 'summary' }]
  for (let index = 0; index < STAGES.length; index++) {
    state = f.store.submit('s1', state.revision, parameters[index], f.software)
    state = f.store.begin('s1', f.software, f.root)
    if (index === 2) {
      assert.equal(fs.existsSync(path.join(state.jobDirectory, 'input', 'partitioned.hm')), true)
      const params = JSON.parse(fs.readFileSync(path.join(state.jobDirectory, 'mesh.parameters.json')))
      assert.equal(params.element_size, 7)
      assert.equal(params.partitioned_model, state.stages[1].artifacts.find(artifact => artifact.role === 'partitioned_model').path)
      assert.equal(params.reference_mesh_k, f.mesh.reference_mesh_k)
      assert.equal(fs.existsSync(path.join(state.jobDirectory, 'mesh.case.json')), false, 'the agent generates case data after inspecting this project model')
    }
    if (index === 3) {
      const config = JSON.parse(fs.readFileSync(path.join(state.jobDirectory, 'solve.case.json')))
      assert.deepEqual(config.placement, { DY: 0, DZ: -2 })
      assert.equal(config.run.endtim, 80)
      assert.equal(config.tether.belt_count, 5)
    }
    const artifacts = outputs(f, state)
    f.store.recordTool('s1', state.executionId, index === 3 ? 'mcp__cae__lsdyna_solve' : 'bash', true)
    state = f.store.complete('s1', state.executionId, artifacts)
    if (STAGES[index].review) {
      assert.equal(state.status, 'review')
      assert.equal(state.current, index)
      assert.throws(() => f.store.begin('s1', f.software, f.root), /用户/)
      state = f.store.confirm('s1', state.revision)
    }
  }
  assert.equal(state.status, 'completed')
  assert.equal(state.stages.filter(stage => stage.status === 'done').length, 6)
})

test('no completion from empty, stale, failed or unexecuted artifacts', t => {
  const f = fixture(t)
  let state = f.setStage(1)
  state = f.store.submit('s1', state.revision, {}, f.software)
  state = f.store.begin('s1', f.software, f.root)
  const artifacts = outputs(f, state)
  assert.throws(() => f.store.complete('s1', state.executionId, artifacts), /工具执行记录/)
  f.store.recordTool('s1', state.executionId, 'write', true)
  assert.throws(() => f.store.complete('s1', state.executionId, artifacts), /工具执行记录/)
  f.store.recordTool('s1', state.executionId, 'bash', true)
  f.file('partition/verification.txt', 'VERIFY_FAIL=4')
  assert.throws(() => f.store.complete('s1', state.executionId, artifacts), /独立回读/)
  f.file('partition/verification.txt', 'VERIFY_FAIL=0')
  fs.utimesSync(artifacts[0].path, new Date(0), new Date(0))
  assert.throws(() => f.store.complete('s1', state.executionId, artifacts), /旧结果/)
  fs.writeFileSync(artifacts[0].path, '')
  assert.throws(() => f.store.complete('s1', state.executionId, artifacts), /为空/)
  assert.throws(() => f.store.complete('s1', 'old-execution', artifacts), /已失效/)
})

test('gate failure and duplicate HyperView views cannot advance the workflow', t => {
  const f = fixture(t)
  let state = f.setStage(4)
  state = f.store.submit('s1', state.revision, { local_d3plot: f.file('d3plot'), start_time: 0, end_time: 80, frames: 21, fps: 10, result_type: 'displacement' }, f.software)
  state = f.store.begin('s1', f.software, f.root)
  f.store.recordTool('s1', state.executionId, 'bash', true)
  const artifacts = outputs(f, state)
  f.file('postprocess/four_views.log', 'unique md5: 1 / 12')
  assert.throws(() => f.store.complete('s1', state.executionId, artifacts), /four_views/)
  assert.equal(f.store.load('s1').status, 'running')
})

test('additional parameters, adjustment and restart recovery retain the current stage', t => {
  const f = fixture(t)
  let state = f.store.create('s1')
  state = f.store.submit('s1', state.revision, f.intake, f.software)
  state = f.store.begin('s1', f.software, f.root)
  state = f.store.requestInput('s1', state.executionId, '请填写本模型的比例系数及依据。')
  assert.equal(state.current, 0)
  assert.throws(() => f.store.submit('s1', state.revision, f.intake, f.software), /补充/)
  state = f.store.submit('s1', state.revision, { ...f.intake, additional_input: '本项目使用 mm，比例为 1' }, f.software)
  state = f.store.begin('s1', f.software, f.root)
  f.store.interruptRunning()
  assert.equal(f.store.load('s1').status, 'interrupted')
  assert.equal(f.store.load('s1').parameters.import.additional_input, '本项目使用 mm，比例为 1')
  const revision = f.store.load('s1').revision
  f.store.recordTool('s1', state.executionId, 'bash', true)
  assert.equal(f.store.load('s1').revision, revision)
  f.setStage(1, 'review')
  state = f.store.load('s1')
  state = f.store.adjust('s1', state.revision, '右侧拉带调整')
  assert.equal(state.status, 'parameters')
  assert.equal(state.feedback, '右侧拉带调整')
})

test('dead process locks recover while live process locks block concurrent writes', t => {
  const f = fixture(t)
  f.store.create('s1')
  const lock = f.store.file('s1') + '.lock'
  fs.writeFileSync(lock, JSON.stringify({ pid: process.pid }))
  assert.throws(() => f.store.create('s1'), /正在更新/)
  fs.writeFileSync(lock, JSON.stringify({ pid: 2147483647 }))
  assert.doesNotThrow(() => f.store.create('s1'))
  assert.equal(fs.existsSync(lock), false)
})

test('remote results require the selected service confirmation and a real solver receipt', t => {
  const f = fixture(t)
  let state = f.setStage(3)
  state = f.store.change('s1', undefined, state => { state.stages[2].artifacts = [{ role: 'curtain_k', path: f.file('curtain.k') }]; return state })
  const software = { ...f.software, solverLocation: 'server', lsdyna: '', solverServerUrl: 'https://solver.example.com' }
  state = f.store.submit('s1', state.revision, { ...f.solve, service_paths_confirmed: true }, software)
  state = f.store.begin('s1', software, f.root)
  const artifacts = outputs(f, state).map(artifact => ['combined_k', 'd3plot'].includes(artifact.role) ? { role: artifact.role, path: `/server/${artifact.role}${artifact.role === 'combined_k' ? '.k' : ''}`, remote: true } : artifact)
  f.store.recordTool('s1', state.executionId, 'bash', true)
  assert.throws(() => f.store.complete('s1', state.executionId, artifacts), /求解后端/)
  f.store.recordTool('s1', state.executionId, 'mcp__cae__lsdyna_solve', true)
  const completed = f.store.complete('s1', state.executionId, artifacts)
  assert.equal(completed.current, 4)
  assert.equal(completed.status, 'parameters')
})

test('interrupted solver retries require the user to verify the existing job first', t => {
  const f = fixture(t)
  let state = f.setStage(3, 'interrupted')
  assert.throws(() => f.store.submit('s1', state.revision, f.solve, f.software), /避免重复求解/)
  state = f.store.submit('s1', state.revision, { ...f.solve, retry_confirmed: true }, f.software)
  assert.equal(state.status, 'ready')
})

test('partition completion rejects a count-only PASS and overlapping or open trial surfaces', t => {
  const f = fixture(t)
  let state = f.setStage(1)
  state = f.store.submit('s1', state.revision, {}, f.software)
  state = f.store.begin('s1', f.software, f.root)
  f.store.recordTool('s1', state.executionId, 'pwsh', true)
  const artifacts = outputs(f, state)
  assert.throws(() => f.store.complete('s1', state.executionId, artifacts.filter(a => a.role !== 'geometry_verification')), /geometry_verification/)
  const model = artifacts.find(a => a.role === 'partitioned_model').path
  const geometry = artifacts.find(a => a.role === 'geometry_verification').path
  for (const metrics of [{ belt_area: 1092034 }, { cavity_boundary_closed: false }, { cut_cavity_area: 1 }, { cavity_area: -1 }]) {
    const report = partitionGeometry(model)
    Object.assign(report.metrics, metrics)
    fs.writeFileSync(geometry, JSON.stringify(report))
    assert.throws(() => f.store.complete('s1', state.executionId, artifacts), /闭环或裁切面积/)
  }
  fs.writeFileSync(geometry, JSON.stringify(partitionGeometry(model)))
  assert.equal(f.store.complete('s1', state.executionId, artifacts).status, 'review')
})

function beginMesh(f) {
  let state = f.setStage(2)
  state = f.store.change('s1', undefined, state => { state.stages[1].artifacts = [{ role: 'partitioned_model', path: f.file('partitioned.hm', 'confirmed partition') }]; return state })
  state = f.store.submit('s1', state.revision, f.mesh, f.software)
  return f.store.begin('s1', f.software, f.root)
}

test('accepted auto_gate WARN remains visible in review without weakening other gates', t => {
  const f = fixture(t)
  const state = beginMesh(f)
  const artifacts = outputs(f, state)
  const k = artifacts.find(a => a.role === 'curtain_k').path
  f.file('mesh/auto_gate.log', autoGate(k, true))
  f.store.recordTool('s1', state.executionId, 'pwsh', true)
  f.file('mesh/quality.log', { verdict: 'WARN' })
  assert.throws(() => f.store.complete('s1', state.executionId, artifacts), /quality/)
  f.file('mesh/quality.log', { verdict: 'PASS' })
  const completed = f.store.complete('s1', state.executionId, artifacts)
  assert.equal(completed.status, 'review')
  assert.deepEqual(completed.stages[2].warnings.map(w => w.name), ['拓扑门禁', '环几何匹配'])
  assert.equal(JSON.parse(fs.readFileSync(path.join(f.directory, 'mesh/auto_gate.log'))).overall, 'WARN')
})

test('mesh retries reuse unchanged old artifacts only with fresh gates and independent HM/K readback', t => {
  const f = fixture(t)
  let state = beginMesh(f)
  const artifacts = outputs(f, state)
  const rolePaths = { mesh_model: 'curtain_mesh.hm', curtain_k: 'curtain_airbag.k', preview: 'mesh_preview.png' }
  for (const artifact of artifacts) {
    if (!rolePaths[artifact.role]) continue
    const file = path.join(state.jobDirectory, 'out', rolePaths[artifact.role])
    fs.copyFileSync(artifact.path, file)
    artifact.path = file
    fs.utimesSync(file, new Date(0), new Date(0))
  }
  const k = artifacts.find(a => a.role === 'curtain_k').path
  const hm = artifacts.find(a => a.role === 'mesh_model').path
  state = f.store.fail('s1', state.executionId, 'Inspect existing results', 'interrupted')
  state = f.store.submit('s1', state.revision, f.mesh, f.software)
  state = f.store.begin('s1', f.software, f.root)
  assert.equal(state.meshRecovery.mode, 'verify_existing')
  assert.equal(JSON.parse(fs.readFileSync(path.join(state.jobDirectory, 'mesh.recovery.json'))).artifacts.length, 3)
  f.store.recordTool('s1', state.executionId, 'pwsh', true)
  f.file('mesh/auto_gate.log', autoGate(k, true))
  const summary = JSON.parse(fs.readFileSync(artifacts.find(a => a.role === 'verification').path))
  assert.throws(() => f.store.complete('s1', state.executionId, artifacts), /mesh_readback/)
  const rawReadback = f.file('mesh/readback.txt', 'independent HM readback fixture')
  const readback = { schema: 'cae.mesh-readback.v1', overall: 'PASS', hm_file: hm, k_file: k, hm_sha256: sha256(hm), k_sha256: sha256(k), readback_file: rawReadback, readback_sha256: sha256(rawReadback), nodes: 82183, elements: 84064, failures: [] }
  const evidence = f.file('mesh/readback.json', readback)
  summary.checks.push({ name: 'mesh_readback', passed: true, evidence })
  fs.writeFileSync(artifacts.find(a => a.role === 'verification').path, JSON.stringify(summary))
  fs.writeFileSync(evidence, JSON.stringify({ ...readback, failures: ['HM did not finish reading'] }))
  assert.throws(() => f.store.complete('s1', state.executionId, artifacts), /独立回读证据/)
  fs.writeFileSync(evidence, JSON.stringify(readback))
  fs.utimesSync(rawReadback, new Date(0), new Date(0))
  assert.throws(() => f.store.complete('s1', state.executionId, artifacts), /独立回读的原始记录/)
  fs.writeFileSync(rawReadback, 'independent HM readback fixture')
  const gateFile = summary.checks[0].evidence
  fs.utimesSync(gateFile, new Date(0), new Date(0))
  assert.throws(() => f.store.complete('s1', state.executionId, artifacts), /本次执行/)
  fs.writeFileSync(gateFile, 'PASS')
  fs.appendFileSync(hm, 'tampered')
  fs.utimesSync(hm, new Date(0), new Date(0))
  assert.throws(() => f.store.complete('s1', state.executionId, artifacts), /旧结果/)
  fs.writeFileSync(hm, 'actual output fixture')
  fs.utimesSync(hm, new Date(0), new Date(0))
  assert.equal(f.store.complete('s1', state.executionId, artifacts).status, 'review')
  assert.equal(fs.statSync(hm).mtimeMs, 0, 'recovery does not refresh output timestamps')
})

test('changed mesh parameters or source partition cannot silently reuse previous outputs', t => {
  const f = fixture(t)
  let state = beginMesh(f)
  for (const name of ['curtain_mesh.hm', 'curtain_airbag.k', 'mesh_preview.png']) f.file(path.relative(f.directory, path.join(state.jobDirectory, 'out', name)))
  state = f.store.fail('s1', state.executionId, 'interrupted fixture')
  state = f.store.submit('s1', state.revision, { ...f.mesh, element_size: 3 }, f.software)
  state = f.store.begin('s1', f.software, f.root)
  assert.equal(state.meshRecovery.mode, 'rebuild')
  state = f.store.fail('s1', state.executionId, 'stopped before replacing old outputs')
  state = f.store.submit('s1', state.revision, { ...f.mesh, element_size: 3 }, f.software)
  state = f.store.begin('s1', f.software, f.root)
  assert.equal(state.meshRecovery.mode, 'rebuild', 'repeated retries cannot attach new parameters to untouched old outputs')
  state = f.store.fail('s1', state.executionId, 'interrupted fixture')
  fs.appendFileSync(state.stages[1].artifacts[0].path, 'changed partition')
  state = f.store.submit('s1', state.revision, { ...f.mesh, element_size: 3 }, f.software)
  state = f.store.begin('s1', f.software, f.root)
  assert.equal(state.meshRecovery.mode, 'rebuild')
  assert.match(state.meshRecovery.reason, /分区模型已变化/)
})

const assert = require('node:assert/strict')
const fs = require('node:fs')
const { join, resolve } = require('node:path')
const { tmpdir } = require('node:os')
const { test } = require('node:test')
const { WorkflowStore } = require('../state.cjs')

test('real dsh tool schema activates; the host binds sessions, gates writes and records actual results', async t => {
  const directory = fs.mkdtempSync(join(tmpdir(), 'cae-workflow-host-'))
  const env = { CAE_WORKFLOW_DIR: directory, CAE_PROJECT_ROOT: resolve(__dirname, '../../..'), CAE_HMBATCH: join(directory, 'hmbatch.exe') }
  const previous = Object.fromEntries(Object.keys(env).map(key => [key, process.env[key]]))
  Object.assign(process.env, env)
  t.after(() => { for (const [key, value] of Object.entries(previous)) { if (value === undefined) delete process.env[key]; else process.env[key] = value }; fs.rmSync(directory, { recursive: true, force: true }) })
  fs.writeFileSync(env.CAE_HMBATCH, 'executable fixture')
  const { apply } = await import('../index.js')
  let tool
  const listeners = new Map()
  apply({ tools: { register: value => { tool = value } }, on: (name, callback) => listeners.set(name, callback) })
  assert.equal(tool.name, 'cae_workflow')
  assert.equal(tool.parameters.properties.action.enum.includes('confirm'), false)
  let concluded = false
  const exec = { agent: { id: 'bound-session' }, signal: new AbortController().signal, concludeTurn: () => { concluded = true } }
  const created = await tool.execute({ action: 'create', sessionId: 'untrusted-other-session' }, exec)
  assert.equal(created.state.sessionId, 'bound-session')
  assert.equal(concluded, true)
  const store = new WorkflowStore(directory)
  assert.equal(store.load('untrusted-other-session'), null)
  const allow = () => Promise.resolve({ kind: 'allow' })
  const gate = listeners.get('tools/pre-execute')
  assert.equal((await gate({ ...exec, name: 'read', arguments: {} }, allow)).kind, 'allow')
  assert.equal((await gate({ ...exec, name: 'bash', arguments: { command: 'cat SKILL.md' } }, allow)).kind, 'allow')
  assert.equal((await gate({ ...exec, name: 'write', arguments: {} }, allow)).kind, 'deny')
  assert.equal((await gate({ ...exec, name: 'mcp__cae__hypermesh_import_igs', arguments: {} }, allow)).kind, 'deny')
  const igs = join(directory, 'current.igs'); fs.writeFileSync(igs, 'geometry fixture')
  store.submit('bound-session', created.state.revision, { project_name: 'Fixture', igs_file: igs, workdir: directory }, { hmbatch: env.CAE_HMBATCH })
  const started = await tool.execute({ action: 'begin' }, exec)
  assert.equal(started.state.status, 'running')
  assert.equal(started.state.parameterFile, join(started.state.jobDirectory, 'import.parameters.json'))
  assert.equal(JSON.parse(fs.readFileSync(started.state.parameterFile, 'utf8')).igs_file, igs)
  assert.equal((await gate({ ...exec, name: 'mcp__cae__hypermesh_partition_airbag', arguments: {} }, allow)).kind, 'deny')
  const around = listeners.get('tools/execute')
  await around({ ...exec, name: 'bash', arguments: { command: 'run fixture' } }, async () => ({ isError: false, value: { exitCode: 1 }, content: [] }))
  assert.equal(store.load('bound-session').toolRuns.at(-1).success, false)
  await around({ ...exec, name: 'bash', arguments: { command: 'run fixture' } }, async () => ({ isError: false, value: { exitCode: 0 }, content: [] }))
  assert.equal(store.load('bound-session').toolRuns.at(-1).success, true)
  listeners.get('agent/status')({ agent: exec.agent, status: 'idle' })
  assert.equal(store.load('bound-session').status, 'interrupted')
})

test('model-facing workflow snapshots leave large case data and tool history on disk', async t => {
  const { workflowView } = await import('../index.js')
  const directory = fs.mkdtempSync(join(tmpdir(), 'cae-workflow-context-'))
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }))
  const store = new WorkflowStore(directory)
  store.create('session')
  const full = store.change('session', undefined, state => {
    state.current = 2
    state.status = 'running'
    state.jobDirectory = directory
    state.executionId = 'current-execution'
    state.skillPath = 'current-skill.md'
    state.error = 'Actual diagnostic to preserve.'
    state.parameters = { mesh: { case_config: { nodes: Array(50000).fill([1, 2, 3]) }, gate_config: { layers: Array(50000).fill(1) } } }
    state.traces = Array(100).fill({ text: 'prior execution history'.repeat(50) })
    state.toolRuns = Array(100).fill({ name: 'bash', success: true })
    state.stages[1].artifacts = [{ role: 'partitioned_model', path: join(directory, 'partitioned.hm') }]
    state.stages[2].warnings = [{ name: '拓扑门禁', summary: 'Short edges', detail: [['最小边 <3mm', { 2: 8 }, 'WARN']], evidence: join(directory, 'auto_gate.json') }]
    return state
  })
  const snapshot = workflowView(full)
  assert.ok(JSON.stringify(full).length > 500000)
  assert.ok(JSON.stringify(snapshot).length < 8000, 'status and begin must not return the entire case repeatedly')
  assert.equal(snapshot.state.parameters, undefined)
  assert.equal(snapshot.state.traces, undefined)
  assert.equal(snapshot.state.toolRuns, undefined)
  assert.equal(snapshot.state.parameterFile, join(directory, 'mesh.parameters.json'))
  assert.equal(snapshot.state.caseFile, join(directory, 'mesh.case.json'))
  assert.equal(snapshot.state.gateFile, join(directory, 'mesh.gate.json'))
  assert.equal(snapshot.state.recoveryFile, join(directory, 'mesh.recovery.json'))
  assert.equal(snapshot.state.executionId, 'current-execution')
  assert.equal(snapshot.state.error, 'Actual diagnostic to preserve.')
  assert.deepEqual(snapshot.state.successfulTools, ['bash'])
  assert.deepEqual(snapshot.state.stages[1].artifacts, full.stages[1].artifacts)
  assert.deepEqual(snapshot.state.stages[2].warnings, full.stages[2].warnings)
  assert.deepEqual(snapshot, JSON.parse(JSON.stringify(snapshot)), 'tool output must remain lossless JSON')
  assert.deepEqual(store.load('session'), full, 'the full persistent state must stay intact')
})

test('MCP warning/error payloads and nonzero subprocess exits cannot be execution proof', async () => {
  const { toolSucceeded } = await import('../policy.js')
  const result = data => ({ isError: false, value: { content: [{ type: 'text', text: JSON.stringify(data) }] }, content: [] })
  assert.equal(toolSucceeded(result({ status: 'ok', exitCode: 0 })), true)
  assert.equal(toolSucceeded(result({ status: 'warning', exitCode: 2 })), false)
  assert.equal(toolSucceeded(result({ status: 'error' })), false)
  assert.equal(toolSucceeded({ isError: true }), false)
})

const assert = require('node:assert/strict')
const { once } = require('node:events')
const { mkdtemp, readFile, rm, writeFile } = require('node:fs/promises')
const { createServer } = require('node:http')
const { createRequire } = require('node:module')
const { tmpdir } = require('node:os')
const { join, resolve } = require('node:path')
const { test } = require('node:test')
const { Script } = require('node:vm')
const {
  DEFAULT_SOLVER_SETTINGS, parseSimulationSettings, simulationEnvironment, checkSolverService,
} = require('../dist/simulation-settings.js')

const legacy = {
  hyperworksHome: '', hmbatch: '', hyperview: '', lsdyna: 'C:\\LSTC\\lsdyna.exe', workdir: 'D:\\jobs',
}

test('existing settings retain local software and allow an assistant-only installation', () => {
  assert.deepEqual(parseSimulationSettings(legacy), { ...legacy, ...DEFAULT_SOLVER_SETTINGS })
  assert.equal(parseSimulationSettings({ ...legacy, lsdyna: '' }).lsdyna, '')
})

test('service modes select their own endpoint and never expose a local solver to the runtime', () => {
  const settings = {
    ...legacy, ...DEFAULT_SOLVER_SETTINGS,
    solverServerUrl: 'https://solver.example/api', solverServerToken: 'remote-token',
    solverLocalServiceUrl: 'http://127.0.0.1:8000', solverLocalServiceToken: 'local-token',
  }
  const local = simulationEnvironment(parseSimulationSettings(settings))
  assert.equal(local.CAE_LSDYNA, legacy.lsdyna)
  assert.equal(local.CAE_SOLVER_SERVICE_URL, '')
  assert.equal(local.CAE_SOLVER_SERVICE_TOKEN, '')

  const server = simulationEnvironment(parseSimulationSettings({ ...settings, solverLocation: 'server' }))
  assert.equal(server.CAE_LSDYNA, '')
  assert.equal(server.CAE_SOLVER_LOCATION, 'server')
  assert.equal(server.CAE_SOLVER_SERVICE_URL, settings.solverServerUrl)
  assert.equal(server.CAE_SOLVER_SERVICE_TOKEN, settings.solverServerToken)

  const service = simulationEnvironment(parseSimulationSettings({ ...settings, localSolverType: 'service' }))
  assert.equal(service.CAE_LSDYNA, '')
  assert.equal(service.CAE_LOCAL_SOLVER_TYPE, 'service')
  assert.equal(service.CAE_SOLVER_SERVICE_URL, settings.solverLocalServiceUrl)
  assert.equal(service.CAE_SOLVER_SERVICE_TOKEN, settings.solverLocalServiceToken)
  assert.equal(settings.lsdyna, legacy.lsdyna)
})

test('validates the selected connection without blocking inactive settings or path checks', () => {
  const settings = { ...legacy, ...DEFAULT_SOLVER_SETTINGS, solverServerUrl: 'unfinished' }
  assert.equal(parseSimulationSettings(settings).solverServerUrl, 'unfinished')
  assert.throws(() => parseSimulationSettings({ ...settings, solverLocation: 'server' }), /求解服务地址/)
  assert.equal(parseSimulationSettings({ ...settings, solverLocation: 'server' }, { validateService: false }).solverLocation, 'server')
  assert.throws(() => parseSimulationSettings({ ...settings, localSolverType: 'service', solverLocalServiceUrl: '' }), /求解服务地址/)

  for (const solverServerUrl of ['', 'https:solver.example', 'ftp://solver.example', 'https://user:secret@solver.example', 'https://solver.example?token=secret', 'https://solver.example#secret', 'http://local\nhost']) {
    assert.throws(() => parseSimulationSettings({ ...legacy, solverLocation: 'server', solverServerUrl }), error => {
      assert.match(error.message, /求解服务地址/)
      assert.equal(error.message.includes('secret'), false)
      return true
    })
  }
  assert.throws(() => parseSimulationSettings({ ...legacy, localSolverType: 'service', solverLocalServiceToken: 'bad\ntoken' }), /令牌/)
})

test('rejects malformed modes and IPC payloads', () => {
  for (const raw of [null, [], 'settings', {}, { ...legacy, solverLocation: 'cloud' }, { ...legacy, localSolverType: 'exe' }, { ...legacy, lsdyna: 42 }, { ...legacy, solverServerToken: 'secret\0' }]) {
    assert.throws(() => parseSimulationSettings(raw))
  }
})

test('saving model or simulation settings preserves both connections and migrates an old settings file', async t => {
  const directory = await mkdtemp(join(tmpdir(), 'cae-store-test-'))
  t.after(() => rm(directory, { recursive: true, force: true }))
  const filename = resolve(__dirname, '../dist/store.js')
  const requireFromStore = createRequire(filename)
  const module = { exports: {} }
  const loadModule = new Script(`(function(require, module, exports) { ${await readFile(filename, 'utf8')}\n})`, { filename }).runInThisContext()
  loadModule(name => name === 'electron' ? { app: { getPath: () => directory } } : requireFromStore(name), module, module.exports)
  const store = module.exports
  const model = { apiKey: 'model-key-test', llmBaseUrl: '', model: 'deepseek-flash' }
  const file = join(directory, 'cae-settings.json')
  await writeFile(file, JSON.stringify({ ...legacy, ...model }))
  assert.equal(store.loadSettings().solverLocation, 'local')
  assert.deepEqual(store.loadSettings().models, ['deepseek-flash'])

  store.saveSettings({ ...store.loadSettings(), models: ['working-model', 'other-model'], solverLocation: 'server', solverServerUrl: 'https://solver.example', solverServerToken: 'remote-token' })
  store.saveSettings({ ...store.loadSettings(), model: 'another-model' })
  assert.equal(store.loadSettings().solverServerToken, 'remote-token')
  store.saveSettings({ ...store.loadSettings(), solverLocation: 'local', localSolverType: 'service', solverLocalServiceToken: 'local-token' })
  const saved = JSON.parse(await readFile(file, 'utf8'))
  assert.equal(saved.apiKey, model.apiKey)
  assert.equal(saved.model, 'another-model')
  assert.deepEqual(saved.models, ['another-model', 'deepseek-flash', 'working-model', 'other-model'])
  assert.equal(saved.lsdyna, legacy.lsdyna)
  assert.equal(saved.solverServerToken, 'remote-token')
  assert.equal(saved.solverLocalServiceToken, 'local-token')
})

test('connection check authenticates a GET health request without submitting a solve', async t => {
  const requests = []
  const endpoint = createServer((request, response) => {
    requests.push({ method: request.method, path: request.url, auth: request.headers.authorization })
    response.writeHead(200, { 'Content-Type': 'application/json' })
    response.end(JSON.stringify({ status: 'ok' }))
  })
  endpoint.listen(0, '127.0.0.1')
  await once(endpoint, 'listening')
  t.after(() => new Promise(resolve => endpoint.close(resolve)))
  const result = await checkSolverService({
    ...legacy, solverLocation: 'server',
    solverServerUrl: `http://127.0.0.1:${endpoint.address().port}/api/`, solverServerToken: 'health-token',
  })
  assert.equal(result.valid, true)
  assert.deepEqual(requests, [{ method: 'GET', path: '/api/health', auth: 'Bearer health-token' }])
})

test('connection check reports an incompatible service and does not leak error bodies', async t => {
  let status = 200
  const endpoint = createServer((_request, response) => {
    response.writeHead(status, { 'Content-Type': 'application/json' })
    response.end(JSON.stringify({ status: 'starting', secret: 'private-response' }))
  })
  endpoint.listen(0, '127.0.0.1')
  await once(endpoint, 'listening')
  t.after(() => new Promise(resolve => endpoint.close(resolve)))
  const settings = { ...legacy, localSolverType: 'service', solverLocalServiceUrl: `http://127.0.0.1:${endpoint.address().port}` }
  assert.equal((await checkSolverService(settings)).valid, false)
  status = 401
  const result = await checkSolverService(settings)
  assert.equal(result.valid, false)
  assert.match(result.message, /401/)
  assert.equal(result.message.includes('private-response'), false)
})

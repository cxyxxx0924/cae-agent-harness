const assert = require('node:assert/strict')
const childProcess = require('node:child_process')
const { EventEmitter } = require('node:events')
const { mkdtemp, mkdir, rm, writeFile } = require('node:fs/promises')
const { tmpdir } = require('node:os')
const { join } = require('node:path')
const { PassThrough } = require('node:stream')
const { test } = require('node:test')
const {
  DEFAULT_WINDOWS_UV_INDEX_URL,
  preparePythonMcpEnvironments,
  pythonMcpFeatureEnvironment,
  pythonMcpProjects,
  stopPythonMcpPreparations,
  uvEnvironment,
} = require('../dist/python-mcp.js')

function settings(overrides = {}) {
  return {
    hyperworksHome: '',
    hmbatch: '',
    hyperview: '',
    lsdyna: '',
    workdir: '',
    solverLocation: 'local',
    localSolverType: 'software',
    solverServerUrl: '',
    solverServerToken: '',
    solverLocalServiceUrl: 'http://127.0.0.1:8000',
    solverLocalServiceToken: '',
    ...overrides,
  }
}

test('optional MCPs are enabled only when their configured paths are usable', async t => {
  const root = await mkdtemp(join(tmpdir(), 'cae-python-mcp-'))
  t.after(() => rm(root, { recursive: true, force: true }))
  const hyperworksHome = join(root, 'Altair')
  const lsdyna = join(root, 'ls971.exe')
  await mkdir(hyperworksHome)
  await mkdir(join(root, 'packages', 'hyperworks-mcp'), { recursive: true })
  await mkdir(join(root, 'packages', 'qilan-solve'), { recursive: true })
  await writeFile(lsdyna, '')

  const configured = settings({ hyperworksHome, lsdyna })
  assert.deepEqual(pythonMcpFeatureEnvironment(configured), {
    CAE_ENABLE_HYPERWORKS_MCP: '1',
    CAE_ENABLE_QILAN_MCP: '1',
  })
  assert.deepEqual(pythonMcpProjects(configured, root).map(project => project.id), ['hyperworks', 'qilan-solve'])
  assert.deepEqual(pythonMcpFeatureEnvironment(settings()), {
    CAE_ENABLE_HYPERWORKS_MCP: '0',
    CAE_ENABLE_QILAN_MCP: '0',
  })
})

test('uv uses the packaged Windows mirror while honoring an explicit index', () => {
  const packaged = uvEnvironment({ PATH: 'path' }, true)
  assert.equal(packaged.UV_INDEX_URL, DEFAULT_WINDOWS_UV_INDEX_URL)
  assert.equal(packaged.UV_DEFAULT_INDEX, DEFAULT_WINDOWS_UV_INDEX_URL)

  const explicit = uvEnvironment({ UV_INDEX_URL: 'https://mirror.example/simple' }, true)
  assert.equal(explicit.UV_INDEX_URL, 'https://mirror.example/simple')
  assert.equal(explicit.UV_DEFAULT_INDEX, 'https://mirror.example/simple')
})

function preparationProcess() {
  return Object.assign(new EventEmitter(), {
    stdout: new PassThrough(),
    stderr: new PassThrough(),
    exitCode: null,
    signalCode: null,
    kill(signal) {
      this.signalCode = signal
      return true
    },
  })
}

test('background preparation allows uv to update PyPI lock URLs for the selected mirror', async t => {
  const root = await mkdtemp(join(tmpdir(), 'cae-python-preparation-'))
  t.after(async () => {
    stopPythonMcpPreparations()
    await rm(root, { recursive: true, force: true })
  })
  const hyperworksHome = join(root, 'Altair')
  await mkdir(hyperworksHome)
  const child = preparationProcess()
  const spawn = t.mock.method(childProcess, 'spawn', () => child)
  const env = uvEnvironment({}, true)

  preparePythonMcpEnvironments(settings({ hyperworksHome }), root, 'uv', env)

  assert.equal(spawn.mock.callCount(), 1)
  const [command, args, options] = spawn.mock.calls[0].arguments
  assert.equal(command, 'uv')
  assert.deepEqual(args, ['sync', '--project', join(root, 'packages', 'hyperworks-mcp')])
  assert.equal(options.env.UV_DEFAULT_INDEX, DEFAULT_WINDOWS_UV_INDEX_URL)
  assert.equal(options.windowsHide, true)
  assert.equal(options.shell, false)
})

test('preparation retries when uv cannot be spawned and emits close without exit', async t => {
  const root = await mkdtemp(join(tmpdir(), 'cae-python-retry-'))
  t.after(async () => {
    stopPythonMcpPreparations()
    await rm(root, { recursive: true, force: true })
  })
  const hyperworksHome = join(root, 'Altair')
  await mkdir(hyperworksHome)
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const children = []
  const spawn = t.mock.method(childProcess, 'spawn', () => {
    const child = preparationProcess()
    children.push(child)
    return child
  })

  preparePythonMcpEnvironments(settings({ hyperworksHome }), root, 'missing-uv', {})
  children[0].emit('error', Object.assign(new Error('spawn missing-uv ENOENT'), { code: 'ENOENT' }))
  children[0].exitCode = -2
  children[0].emit('close', -2)
  t.mock.timers.tick(30_000)

  assert.equal(spawn.mock.callCount(), 2)
  stopPythonMcpPreparations()
  assert.equal(children[1].signalCode, 'SIGTERM')
  t.mock.timers.tick(30_000)
  assert.equal(spawn.mock.callCount(), 2)
})

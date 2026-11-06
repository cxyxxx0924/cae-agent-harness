const assert = require('node:assert/strict')
const { spawn } = require('node:child_process')
const { once } = require('node:events')
const { mkdtemp, rm, writeFile } = require('node:fs/promises')
const { createServer } = require('node:http')
const { tmpdir } = require('node:os')
const { join, resolve } = require('node:path')
const { test } = require('node:test')
const { checkDshPort, waitForDsh } = require('../dist/dsh-startup.js')

async function endpoint(t, handler) {
  const server = createServer(handler)
  server.listen(0, '127.0.0.1')
  await once(server, 'listening')
  t.after(() => new Promise(resolve => server.close(resolve)))
  return `http://127.0.0.1:${server.address().port}`
}

function child(t, script) {
  const proc = spawn(process.execPath, ['-e', script], { stdio: ['ignore', 'pipe', 'pipe'] })
  t.after(async () => {
    if (proc.exitCode !== null || proc.signalCode !== null) return
    const exited = once(proc, 'exit')
    proc.kill('SIGKILL')
    await exited
  })
  return proc
}

test('startup waits for a complete URL line and validates its authentication cookie', async t => {
  const origin = await endpoint(t, (req, res) => {
    assert.equal(req.url, '/?token=startup-test')
    res.writeHead(303, { 'set-cookie': 'session=test', location: './' })
    res.end()
  })
  const proc = child(t, `
    console.log('dsh web: http://[malformed/?token=bad');
    console.log('dsh web: http://untrusted.invalid/?token=bad');
    process.stdout.write('dsh web: ${origin}/?token=');
    setTimeout(() => console.log('startup-test'), 10);
    setInterval(() => {}, 1000);
  `)
  assert.equal(await waitForDsh(proc, origin, 3000), `${origin}/?token=startup-test`)
  assert.equal(proc.listenerCount('error'), 0)
  assert.equal(proc.stdout.listenerCount('error'), 0)
})

test('a URL announcement without successful authentication cannot complete startup', async t => {
  const origin = await endpoint(t, (_req, res) => {
    res.writeHead(401)
    res.end()
  })
  const proc = child(t, `console.log('dsh web: ${origin}/?token=test'); setInterval(() => {}, 1000)`)
  await assert.rejects(waitForDsh(proc, origin, 3000), /authentication failed \(HTTP 401\)/)
})

test('an early dsh exit is reported immediately instead of waiting for the startup timeout', async t => {
  const proc = child(t, 'process.exit(7)')
  await assert.rejects(waitForDsh(proc, 'http://127.0.0.1:3080', 3000), /exited before startup completed \(7\)/)
})

test('a missing executable reports the spawn failure', async () => {
  const proc = spawn(join(tmpdir(), 'cae-missing-node', 'node.exe'), [], { stdio: ['ignore', 'pipe', 'pipe'] })
  await assert.rejects(waitForDsh(proc, 'http://127.0.0.1:3080', 3000), /ENOENT/)
})

test('a stalled startup times out and releases its listeners', async t => {
  const proc = child(t, 'setInterval(() => {}, 1000)')
  await assert.rejects(waitForDsh(proc, 'http://127.0.0.1:3080', 100), /did not start within 100ms/)
  assert.equal(proc.listenerCount('error'), 0)
  assert.equal(proc.listenerCount('exit'), 0)
})

test('a busy port fails before spawning dsh', async t => {
  const origin = await endpoint(t, (_req, res) => res.end())
  const port = Number(new URL(origin).port)
  await assert.rejects(checkDshPort(port), /已被占用/)
  for (const invalid of [NaN, 0, -1, 65536, 1.5]) {
    await assert.rejects(checkDshPort(invalid), /DSH_PORT/)
  }
})

test('the actual dsh CLI reaches authenticated readiness with the CAE profile', { timeout: 20_000 }, async t => {
  const home = await mkdtemp(join(tmpdir(), 'cae-startup-smoke-'))
  t.after(() => rm(home, { recursive: true, force: true }))
  const reservation = createServer()
  reservation.listen(0, '127.0.0.1')
  await once(reservation, 'listening')
  const port = reservation.address().port
  await new Promise(resolve => reservation.close(resolve))
  await checkDshPort(port)
  const patch = join(home, 'test.patch.yml')
  await writeFile(patch, '- id: mcp-cae\n  disabled: true\n')
  const root = resolve(__dirname, '../../..')
  const bin = resolve(require.resolve('@deepseek-ai/dsh/package.json'), '../lib/bin.js')
  const proc = spawn(process.execPath, [
    bin, 'web', '--patch', join(root, 'config/cae-airbag.cordis.yml'), '--patch', patch,
    '--host', '127.0.0.1', '--port', String(port), '--no-open',
  ], {
    cwd: root,
    env: {
      ...process.env, DSH_HOME: home, DSH_TELEMETRY_DISABLED: '1',
      DEEPSEEK_API_KEY: 'sk-startup-smoke-only', LLM_MODEL: 'deepseek-chat',
      CAE_ENABLE_HYPERWORKS_MCP: '0', CAE_ENABLE_QILAN_MCP: '0',
    },
    stdio: ['ignore', process.platform === 'win32' ? 'overlapped' : 'pipe', 'pipe'],
    windowsHide: true,
  })
  t.after(async () => {
    if (proc.exitCode !== null || proc.signalCode !== null) return
    const exited = once(proc, 'exit')
    proc.kill('SIGKILL')
    await exited
  })
  let stderr = ''
  proc.stderr.on('data', chunk => { stderr += chunk })
  const origin = `http://127.0.0.1:${port}`
  try {
    const url = new URL(await waitForDsh(proc, origin, 15_000))
    assert.equal(url.origin, origin)
    assert.ok(url.searchParams.get('token'))
  } catch (error) {
    throw new Error(`${error.message}\n${stderr}`)
  }
})

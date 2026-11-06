const assert = require('node:assert/strict')
const { once } = require('node:events')
const { mkdtemp, writeFile, rm } = require('node:fs/promises')
const { createServer } = require('node:http')
const { tmpdir } = require('node:os')
const { join } = require('node:path')
const { test } = require('node:test')
const { CAE_CONFIG } = require('../dist/config.js')
const subprocess = require('../dist/subprocess.js')
const { solveLsDyna, SolveSchema } = require('../dist/tools/lsdyna.js')

async function service(t, handler) {
  const requests = []
  const endpoint = createServer(async (request, response) => {
    const chunks = []
    for await (const chunk of request) chunks.push(chunk)
    requests.push({
      path: request.url, method: request.method, authorization: request.headers.authorization,
      body: chunks.length ? JSON.parse(Buffer.concat(chunks).toString('utf8')) : null,
    })
    handler(response)
  })
  endpoint.listen(0, '127.0.0.1')
  await once(endpoint, 'listening')
  t.after(() => new Promise(resolve => endpoint.close(resolve)))
  return { url: `http://127.0.0.1:${endpoint.address().port}`, requests }
}

function backend(t, overrides) {
  const previous = { solver: CAE_CONFIG.solver, lsdyna: CAE_CONFIG.lsdyna }
  t.after(() => Object.assign(CAE_CONFIG, previous))
  CAE_CONFIG.solver = { location: 'local', localType: 'software', serviceUrl: '', serviceToken: '', ...overrides }
}

for (const location of ['server', 'local']) {
  test(`${location} service receives solver arguments without requiring client-side files or launching local software`, async t => {
    const { url, requests } = await service(t, response => {
      response.writeHead(200, { 'Content-Type': 'application/json' })
      response.end(JSON.stringify({ status: 'ok', exitCode: 0, d3plot: 'Z:\\jobs\\d3plot', log: 'finished' }))
    })
    backend(t, { location, localType: 'service', serviceUrl: `${url}/api/`, serviceToken: 'test-solver-token' })
    const spawn = t.mock.method(subprocess, 'runProcess', () => { throw new Error('Local solver must not run') })
    const args = SolveSchema.parse({ keyword_file: 'Z:\\server-only\\main.k', ncpu: 8, memory: '4g', output_dir: 'Z:\\jobs' })
    const result = JSON.parse(await solveLsDyna(args))
    assert.equal(result.status, 'ok')
    assert.equal(result.backend, location === 'server' ? 'server' : 'local-service')
    assert.equal(result.d3plot, 'Z:\\jobs\\d3plot')
    assert.equal(spawn.mock.callCount(), 0)
    assert.deepEqual(requests, [{ path: '/api/solve', method: 'POST', authorization: 'Bearer test-solver-token', body: { solver: 'lsdyna', ...args } }])
  })
}

test('local software keeps the existing process invocation and result parsing', async t => {
  backend(t, {})
  CAE_CONFIG.lsdyna = 'local-lsdyna.exe'
  const directory = await mkdtemp(join(tmpdir(), 'cae-solver-test-'))
  t.after(() => rm(directory, { recursive: true, force: true }))
  const keyword = join(directory, 'main.k')
  await writeFile(keyword, '$ termination time = 60\n*KEYWORD\n*END\n')
  const calls = []
  t.mock.method(subprocess, 'runProcess', async (...args) => {
    calls.push(args)
    return { stdout: 't=60 dt=1e-6 flush i=300', stderr: '', exitCode: 0 }
  })
  const result = JSON.parse(await solveLsDyna(SolveSchema.parse({ keyword_file: keyword })))
  assert.equal(result.backend, 'local-software')
  assert.equal(result.status, 'ok')
  assert.equal(result.lastSimTime, 60)
  assert.equal(calls.length, 1)
  assert.equal(calls[0][0], CAE_CONFIG.lsdyna)
  assert.deepEqual(calls[0][1], [`i=${keyword}`, 'ncpu=4', 'memory=2000m'])
  assert.equal(calls[0][2].cwd, directory)
  assert.ok(calls[0][2].timeoutMs >= 24 * 60 * 60 * 1000, 'multi-hour runs must not stop after one hour')
})

test('local nonzero solver exit is an error even when the final log has no error marker', async t => {
  backend(t, {})
  CAE_CONFIG.lsdyna = 'local-lsdyna.exe'
  const directory = await mkdtemp(join(tmpdir(), 'cae-solver-error-'))
  t.after(() => rm(directory, { recursive: true, force: true }))
  const keyword = join(directory, 'main.k')
  await writeFile(keyword, '*KEYWORD\n*END\n')
  t.mock.method(subprocess, 'runProcess', async () => ({ stdout: 'license unavailable', stderr: '', exitCode: 2 }))
  await assert.rejects(solveLsDyna(SolveSchema.parse({ keyword_file: keyword })), /exit 2/)
})

test('invalid mode and missing executable fail instead of falling back to another backend', async t => {
  backend(t, { location: 'unexpected' })
  await assert.rejects(solveLsDyna(SolveSchema.parse({ keyword_file: 'main.k' })), /求解器配置无效/)
  CAE_CONFIG.solver.location = 'local'
  CAE_CONFIG.lsdyna = ''
  await assert.rejects(solveLsDyna(SolveSchema.parse({ keyword_file: 'main.k' })), /尚未配置本地求解器/)
})

test('service failures and malformed responses are not reported as completed solves', async t => {
  let status = 401
  let body = 'secret-response-body'
  const { url } = await service(t, response => {
    response.writeHead(status, { 'Content-Type': 'application/json' })
    response.end(body)
  })
  backend(t, { location: 'server', serviceUrl: url })
  const args = SolveSchema.parse({ keyword_file: '/server/main.k' })
  await assert.rejects(solveLsDyna(args), error => {
    assert.match(error.message, /HTTP 401/)
    assert.equal(error.message.includes('secret-response-body'), false)
    return true
  })
  status = 200
  await assert.rejects(solveLsDyna(args), /返回格式无效/)
  body = JSON.stringify({ status: 'queued', job_id: 'not-complete' })
  await assert.rejects(solveLsDyna(args), /返回格式无效/)
  body = JSON.stringify({ status: 'error', message: 'license unavailable' })
  await assert.rejects(solveLsDyna(args), /license unavailable/)
  body = JSON.stringify({ status: 'ok', exitCode: 2 })
  assert.equal(JSON.parse(await solveLsDyna(args)).status, 'warning')
})

test('tokens are optional, redacted from service logs and never forwarded through redirects', async t => {
  let body = JSON.stringify({ status: 'ok', log: 'done' })
  let redirect
  const { url, requests } = await service(t, response => {
    response.writeHead(redirect ? 302 : 200, redirect ? { Location: redirect } : { 'Content-Type': 'application/json' })
    response.end(body)
  })
  backend(t, { location: 'server', serviceUrl: url })
  const args = SolveSchema.parse({ keyword_file: '/server/main.k' })
  await solveLsDyna(args)
  assert.equal(requests[0].authorization, undefined)
  CAE_CONFIG.solver.serviceToken = 'private-test-token'
  body = JSON.stringify({ status: 'ok', log: 'private-test-token in logs' })
  assert.equal((await solveLsDyna(args)).includes('private-test-token'), false)
  redirect = `${url}/elsewhere`
  await assert.rejects(solveLsDyna(args), /连接中断/)
  assert.equal(requests.length, 3)
})

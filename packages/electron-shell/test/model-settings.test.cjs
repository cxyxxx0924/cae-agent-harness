const assert = require('node:assert/strict')
const { test } = require('node:test')
const { once } = require('node:events')
const { createServer } = require('node:http')
const { DEFAULT_MODEL, parseModelSettings, parseModelConfiguration, modelEnvironment, discoverModels, testModels } = require('../dist/model-settings.js')

const validSettings = {
  apiKey: 'sk-test-only',
  llmBaseUrl: 'https://api.deepseek.com/v1',
  model: 'deepseek-flash',
}

test('unconfigured and invalid desktop models start with no inherited credentials or advertised models', () => {
  for (const settings of [
    { ...validSettings, apiKey: '', models: [], availableModels: [] },
    { ...validSettings, models: ['other-model'] },
    { ...validSettings, llmBaseUrl: 'unfinished' },
    null,
  ]) {
    const env = { DEEPSEEK_API_KEY: 'inherited-key', LLM_MODEL: 'inherited-model', ...modelEnvironment(settings) }
    assert.equal(env.CAE_MODELS_CONFIGURED, '0')
    assert.equal(env.DEEPSEEK_API_KEY, '')
    assert.equal(env.LLM_MODEL, '')
    assert.equal(env.LLM_BASE_URL, '')
    assert.equal(env.CAE_MODELS, '[]')
  }
  const env = modelEnvironment(validSettings)
  assert.equal(env.CAE_MODELS_CONFIGURED, '1')
  assert.equal(env.DEEPSEEK_API_KEY, validSettings.apiKey)
  assert.equal(env.LLM_MODEL, validSettings.model)
  assert.deepEqual(JSON.parse(env.CAE_MODELS), [validSettings.model])
})

test('accepts saved model settings and trims pasted whitespace', () => {
  assert.deepEqual(parseModelSettings({
    apiKey: ' sk-test-only\n',
    llmBaseUrl: ' https://gateway.example/v1 ',
    model: ' qwen3-coder:32b ',
    workdir: '/tmp/cae',
  }), {
    apiKey: 'sk-test-only',
    llmBaseUrl: 'https://gateway.example/v1',
    model: 'qwen3-coder:32b',
  })
})

test('uses the deployment default when the model ID is blank', () => {
  assert.equal(parseModelSettings({ ...validSettings, model: ' ' }).model, DEFAULT_MODEL)
})

test('allows a default endpoint and a local Ollama endpoint', () => {
  assert.equal(parseModelSettings({ ...validSettings, llmBaseUrl: '' }).llmBaseUrl, '')
  assert.equal(parseModelSettings({
    ...validSettings,
    apiKey: 'ollama',
    llmBaseUrl: 'http://localhost:11434/v1',
  }).apiKey, 'ollama')
})

test('rejects swapped credentials without echoing the secret', () => {
  assert.throws(() => parseModelSettings({
    ...validSettings,
    apiKey: validSettings.llmBaseUrl,
    llmBaseUrl: validSettings.apiKey,
  }), /API Key.*API Base URL/)
  assert.throws(() => parseModelSettings({ ...validSettings, llmBaseUrl: validSettings.apiKey }), error => {
    assert.match(error.message, /API Base URL/)
    assert.equal(error.message.includes(validSettings.apiKey), false)
    return true
  })
})

test('rejects malformed endpoints and credentials embedded in URLs', () => {
  for (const llmBaseUrl of [
    'api.deepseek.com/v1',
    'https:api.deepseek.com/v1',
    'https://api.deepseek.com/\nv1',
    'ftp://gateway.example/v1',
    'file:///tmp/model',
    'https://user:password@gateway.example/v1',
    'https://gateway.example/v1?api_key=secret',
    'https://gateway.example/v1#secret',
  ]) {
    assert.throws(() => parseModelSettings({ ...validSettings, llmBaseUrl }), /API Base URL/)
  }
})

test('rejects missing credentials and whitespace in keys or model IDs', () => {
  assert.throws(() => parseModelSettings({ ...validSettings, apiKey: ' ' }), /API Key/)
  assert.throws(() => parseModelSettings({ ...validSettings, apiKey: 'sk-test only' }), /API Key/)
  assert.throws(() => parseModelSettings({ ...validSettings, model: 'qwen max' }), /模型 ID/)
})

test('rejects malformed IPC payloads', () => {
  for (const raw of [null, [], 'settings', {}, { ...validSettings, model: 1 }, { ...validSettings, apiKey: 'key\0' }]) {
    assert.throws(() => parseModelSettings(raw), /模型配置/)
  }
})

test('migrates a single saved model and validates selected models against the available catalog', () => {
  assert.deepEqual(parseModelConfiguration(validSettings).models, ['deepseek-flash'])
  assert.deepEqual(parseModelConfiguration(validSettings).availableModels, ['deepseek-flash'])
  assert.deepEqual(parseModelConfiguration({
    ...validSettings, models: [' working-model ', 'deepseek-flash', 'working-model'],
  }).models, ['working-model', 'deepseek-flash'])
  for (const models of [null, 'model', [null], [''], ['bad model'], ['bad\0model'], Array(1001).fill('model')]) {
    assert.throws(() => parseModelConfiguration({ ...validSettings, models }), /模型列表/)
  }
  assert.throws(() => parseModelConfiguration({ ...validSettings, models: [] }), /至少选择一个模型/)
  assert.throws(() => parseModelConfiguration({ ...validSettings, models: ['working-model'] }), /已选模型/)
  assert.throws(() => parseModelConfiguration({ ...validSettings, models: [validSettings.model], availableModels: ['working-model'] }), /当前接口/)
  const selected = parseModelConfiguration({ ...validSettings, models: [validSettings.model], availableModels: [validSettings.model, 'unselected-model'] })
  assert.deepEqual(selected.models, [validSettings.model])
  assert.deepEqual(selected.availableModels, [validSettings.model, 'unselected-model'])
})

test('discovers alternatives without requesting the unavailable default model', async t => {
  const requests = []
  const endpoint = createServer((request, response) => {
    requests.push({ method: request.method, path: request.url, authorization: request.headers.authorization })
    response.writeHead(200, { 'Content-Type': 'application/json' })
    response.end(JSON.stringify({ data: [{ id: 'working-model' }, { id: 'other-model' }, { id: 'working-model' }, { id: 'invalid model' }] }))
  })
  endpoint.listen(0, '127.0.0.1')
  await once(endpoint, 'listening')
  t.after(() => new Promise(resolve => endpoint.close(resolve)))
  assert.deepEqual(await discoverModels({
    ...validSettings, model: 'invalid model', llmBaseUrl: `http://127.0.0.1:${endpoint.address().port}/gateway/v1/`,
  }), ['working-model', 'other-model'])
  assert.deepEqual(requests, [{ method: 'GET', path: '/gateway/v1/models', authorization: 'Bearer sk-test-only' }])
})

test('discovery failures preserve saved models and do not expose response secrets', async t => {
  let status = 401
  let body = '{"error":"private-response"}'
  const endpoint = createServer((_request, response) => {
    response.writeHead(status, { 'Content-Type': 'application/json' })
    response.end(body)
  })
  endpoint.listen(0, '127.0.0.1')
  await once(endpoint, 'listening')
  t.after(() => new Promise(resolve => endpoint.close(resolve)))
  const settings = { ...validSettings, llmBaseUrl: `http://127.0.0.1:${endpoint.address().port}` }
  await assert.rejects(discoverModels(settings), error => {
    assert.match(error.message, /HTTP 401/)
    assert.equal(error.message.includes('private-response'), false)
    return true
  })
  status = 200
  for (body of ['{}', 'not-json']) {
    await assert.rejects(discoverModels(settings), /有效的模型列表/)
  }
  body = '{"data":[]}'
  assert.deepEqual(await discoverModels(settings), [])
})

test('tests selected models and only removes definitive model failures, retaining transient errors', async t => {
  const requests = []
  const endpoint = createServer(async (request, response) => {
    const chunks = []
    for await (const chunk of request) chunks.push(chunk)
    const body = JSON.parse(Buffer.concat(chunks).toString('utf8'))
    requests.push({ path: request.url, auth: request.headers.authorization, body })
    const fixtures = {
      working: [200, { choices: [{ message: { content: 'ok' } }] }],
      missing: [404, { error: { code: 'model_not_found', message: 'private-response' } }],
      forbidden: [403, { error: { message: 'You do not have access to model forbidden' } }],
      embedding: [400, { error: { message: 'This model is not supported in the v1/chat/completions endpoint' } }],
      limited: [429, { error: { message: 'private-response' } }],
      auth: [401, { error: { message: 'private-response' } }],
      gateway: [404, { error: { message: 'route not found' } }],
      parameter: [400, { error: { message: 'unsupported parameter max_tokens' } }],
      malformed: [200, { error: 'not a chat response' }],
    }
    const [status, result] = fixtures[body.model]
    response.writeHead(status, { 'Content-Type': 'application/json' })
    response.end(JSON.stringify(result))
  })
  endpoint.listen(0, '127.0.0.1')
  await once(endpoint, 'listening')
  t.after(() => new Promise(resolve => endpoint.close(resolve)))
  const models = ['working', 'missing', 'forbidden', 'embedding', 'limited', 'auth', 'gateway', 'parameter', 'malformed']
  const settings = { ...validSettings, model: 'working', models, llmBaseUrl: `http://127.0.0.1:${endpoint.address().port}/v1/` }
  const results = await testModels(settings)
  assert.deepEqual(results.map(result => result.status), ['available', 'unavailable', 'unavailable', 'unavailable', 'unknown', 'unknown', 'unknown', 'unknown', 'unknown'])
  assert.equal(JSON.stringify(results).includes('private-response'), false)
  assert.equal(requests.length, models.length)
  assert.ok(requests.every(request => request.path === '/v1/chat/completions' && request.auth === 'Bearer sk-test-only' && request.body.max_tokens === 1 && request.body.stream === false))
  await assert.rejects(testModels({ ...settings, models: Array.from({ length: 51 }, (_, index) => index ? `model-${index}` : 'working') }), /最多测试 50/)
})

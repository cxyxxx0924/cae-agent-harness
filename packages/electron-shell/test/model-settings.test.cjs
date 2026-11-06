const assert = require('node:assert/strict')
const { test } = require('node:test')
const { once } = require('node:events')
const { createServer } = require('node:http')
const { DEFAULT_MODEL, parseModelSettings, parseModelConfiguration, discoverModels } = require('../dist/model-settings.js')

const validSettings = {
  apiKey: 'sk-test-only',
  llmBaseUrl: 'https://api.deepseek.com/v1',
  model: 'deepseek-flash',
}

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

test('migrates a single saved model and retains the default alongside deduplicated alternatives', () => {
  assert.deepEqual(parseModelConfiguration(validSettings).models, ['deepseek-flash'])
  assert.deepEqual(parseModelConfiguration({
    ...validSettings, models: [' working-model ', 'deepseek-flash', 'working-model'],
  }).models, ['deepseek-flash', 'working-model'])
  for (const models of [null, 'model', [null], [''], ['bad model'], ['bad\0model'], Array(1001).fill('model')]) {
    assert.throws(() => parseModelConfiguration({ ...validSettings, models }), /模型列表/)
  }
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

test('discovery failures allow manual configuration and do not expose response secrets', async t => {
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
  for (body of ['{}', '{"data":[]}', 'not-json']) {
    await assert.rejects(discoverModels(settings), /手动填写模型 ID/)
  }
})

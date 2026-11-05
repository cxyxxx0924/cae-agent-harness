const assert = require('node:assert/strict')
const { test } = require('node:test')
const { DEFAULT_MODEL, parseModelSettings } = require('../dist/model-settings.js')

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

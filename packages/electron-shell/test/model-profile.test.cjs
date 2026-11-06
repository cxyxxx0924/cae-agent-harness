const assert = require('node:assert/strict')
const { randomUUID } = require('node:crypto')
const { once } = require('node:events')
const { mkdtemp, readFile, writeFile, rm } = require('node:fs/promises')
const { createServer } = require('node:http')
const { createRequire } = require('node:module')
const { tmpdir } = require('node:os')
const { join, resolve } = require('node:path')
const { test } = require('node:test')
const { pathToFileURL } = require('node:url')

async function startModelRuntime(t, model, models = [], configured = true) {
  const temporaryHome = await mkdtemp(join(tmpdir(), 'cae-model-test-'))
  const previous = {}
  let ctx
  t.after(async () => {
    try {
      await ctx?.fiber.dispose()
    } finally {
      if (endpoint.listening) await new Promise(resolve => endpoint.close(resolve))
      for (const [key, value] of Object.entries(previous)) {
        if (value === undefined) delete process.env[key]
        else process.env[key] = value
      }
      await rm(temporaryHome, { recursive: true, force: true })
    }
  })

  const received = []
  const endpoint = createServer(async (request, response) => {
    const chunks = []
    for await (const chunk of request) chunks.push(chunk)
    received.push({
      path: request.url,
      authorization: request.headers.authorization,
      body: JSON.parse(Buffer.concat(chunks).toString('utf8')),
    })
    if (received.at(-1).body.model === 'missing-model') {
      response.writeHead(404, { 'Content-Type': 'application/json' })
      response.end(JSON.stringify({ error: { message: 'model does not exist', type: 'invalid_request_error' } }))
      return
    }
    response.writeHead(200, { 'Content-Type': 'text/event-stream' })
    const inputTokens = Math.ceil(JSON.stringify(received.at(-1).body).length / 4)
    response.end([
      `data: ${JSON.stringify({
        id: 'smoke-completion',
        object: 'chat.completion.chunk',
        created: 1,
        model,
        choices: [{ index: 0, delta: { role: 'assistant', content: 'configured-ok' }, finish_reason: null }],
      })}\n\n`,
      `data: ${JSON.stringify({ choices: [{ index: 0, delta: {}, finish_reason: 'stop' }] })}\n\n`,
      `data: ${JSON.stringify({ choices: [], usage: { prompt_tokens: inputTokens, completion_tokens: 3, total_tokens: inputTokens + 3 } })}\n\n`,
      'data: [DONE]\n\n',
    ].join(''))
  })
  endpoint.listen(0, '127.0.0.1')
  await once(endpoint, 'listening')

  const portReservation = createServer()
  portReservation.listen(0, '127.0.0.1')
  await once(portReservation, 'listening')
  const webPort = portReservation.address().port
  await new Promise(resolve => portReservation.close(resolve))

  const overrides = {
    DSH_HOME: temporaryHome,
    DSH_TELEMETRY_DISABLED: '1',
    DSH_NO_OPEN_BROWSER: '1',
    DEEPSEEK_API_KEY: 'sk-cae-model-test-only',
    LLM_BASE_URL: `http://127.0.0.1:${endpoint.address().port}/v1`,
    LLM_MODEL: model,
    CAE_MODELS: JSON.stringify(models),
    CAE_DESKTOP: '1',
    CAE_MODELS_CONFIGURED: configured ? '1' : '0',
    CAE_WORKFLOW_DIR: join(temporaryHome, 'workflows'),
    HYPERWORKS_HOME: '',
    CAE_LSDYNA: '',
  }
  Object.assign(previous, Object.fromEntries(Object.keys(overrides).map(key => [key, process.env[key]])))
  Object.assign(process.env, overrides)

  const patch = join(temporaryHome, 'test.patch.yml')
  await writeFile(patch, '- id: mcp-cae\n  disabled: true\n')
  const dshRequire = createRequire(require.resolve('@deepseek-ai/dsh/package.json'))
  const { createLaunchEnvironmentSnapshot } = await import(pathToFileURL(dshRequire.resolve('@deepseek-ai/dsh-launch-environment')).href)
  const { runProfile } = await import('@deepseek-ai/dsh/profile-boot')
  const runtime = await runProfile({
    environment: createLaunchEnvironmentSnapshot([{ source: 'process', values: process.env }]),
    profile: 'web',
    patchFiles: [resolve(__dirname, '../../../config/cae-airbag.cordis.yml'), patch],
    args: ['--host', '127.0.0.1', '--port', String(webPort), '--no-open'],
  })
  ctx = runtime.ctx
  return { ctx, received }
}

async function prompt(ctx, sessionId, text) {
  await ctx.sessionController.prompt({
    sessionId, requestId: `test-${randomUUID()}`, mode: 'queue',
    content: [{ type: 'text', text }],
  }, AbortSignal.timeout(15000))
  const agent = ctx.agents.get(sessionId)
  await agent.whenIdle()
  return agent
}

test('a 64K model automatically compacts long completed turns before the next request', { timeout: 30000 }, async t => {
  const { ctx, received } = await startModelRuntime(t, 'configured-model')
  const { sessionId } = await ctx.sessionController.create({})
  assert.equal((await ctx.llm.resolveModelInfo('cae', 'configured-model')).context.contextWindow, 65536)
  const payload = 'completed engineering evidence. '.repeat(2400)
  for (let turn = 0; turn < 3; turn++) await prompt(ctx, sessionId, `turn ${turn}: ${payload}`)
  const agent = await prompt(ctx, sessionId, 'Continue using the confirmed project inputs.')
  const summaries = agent.session.snapshotEvents().filter(event => event.type === 'compaction/summary')
  assert.ok(summaries.length, 'automatic compaction must run for the 64K fallback model')
  assert.ok(received.length > 4, 'history summarization must use a real routed model request')
  const finalRequest = received.at(-1).body
  assert.ok(JSON.stringify(finalRequest).length < 65536 * 4 * 0.7, 'the next request must stay below the compaction threshold')
  assert.ok(ctx.tokenMeter.measure(agent.session).totalTokens < 65536 * 0.7)
  assert.ok(ctx.commands.list(agent).some(command => command.name === 'compact'))
  const manual = await ctx.commands.execute(agent, '/compact', [], AbortSignal.timeout(10000))
  assert.equal(manual.result.kind, 'success')
  assert.match(manual.result.text, /^Compacted /, 'the native command must also compact below the automatic threshold')
  const second = await ctx.sessionController.create({})
  const secondAgent = await prompt(ctx, second.sessionId, 'A new independent project.')
  assert.equal(secondAgent.session.snapshotEvents().filter(event => event.type === 'compaction/summary').length, 0)
  assert.ok(ctx.tokenMeter.measure(secondAgent.session).totalTokens < 10000, 'new conversations must not inherit previous context')
})

test('oversized tool output keeps a bounded preview and a recoverable full result', { timeout: 30000 }, async t => {
  const { ctx } = await startModelRuntime(t, 'configured-model')
  const { sessionId } = await ctx.sessionController.create({})
  const dshRequire = createRequire(require.resolve('@deepseek-ai/dsh/package.json'))
  const { defineTool } = await import(pathToFileURL(dshRequire.resolve('@deepseek-ai/dsh-tools')).href)
  const fullOutput = 'solver detail\n'.repeat(12000)
  ctx.tools.register(defineTool({
    name: 'context_fixture', description: 'A large output fixture.', parameters: {},
    output: { schema: { type: 'string' }, render: (_args, value) => [{ type: 'text', text: value }] },
    execute: async () => fullOutput,
  }))
  const result = await ctx.tools.execute({
    callId: 'large-output', name: 'context_fixture', arguments: {},
    agent: ctx.agents.get(sessionId), signal: AbortSignal.timeout(10000),
  })
  assert.equal(result.isError, false)
  assert.equal(result.value, fullOutput, 'canonical data must stay intact')
  const preview = result.content.filter(block => block.type === 'text').map(block => block.text).join('\n')
  assert.ok(preview.length < 4096 * 4)
  const saved = preview.match(/Full formatted result stored at: (.*?)\. /)
  assert.ok(saved, 'truncation must identify the full result')
  assert.equal(await readFile(saved[1], 'utf8'), fullOutput)
  const workflow = await ctx.tools.execute({
    callId: 'create-workflow', name: 'cae_workflow', arguments: { action: 'create' },
    agent: ctx.agents.get(sessionId), signal: AbortSignal.timeout(10000),
  })
  assert.equal(workflow.isError, false, 'compact workflow results must remain valid canonical JSON')
  assert.equal(workflow.value.state.status, 'parameters')
})

test('an unconfigured desktop runtime starts with an empty catalog and can browse a blank session', { timeout: 30000 }, async t => {
  const { ctx, received } = await startModelRuntime(t, 'inherited-model', ['inherited-model'], false)
  const client = ctx.clientModules.graph().entries.find(entry => entry.id === '@cae/dsh-ui')
  assert.ok(client, 'desktop model settings must load even before a model is configured')
  assert.ok(client.inject.includes('@deepseek-ai/dsh-client-ui-settings-general'))
  const bundle = await ctx.clientModules.fetchBundle({ method: 'GET', url: `http://localhost/${client.url}` })
  assert.equal(bundle.status, 200)
  assert.match(await bundle.text(), /cae-models-title/)
  assert.ok(ctx.tools.get('cae_workflow'), 'workflow host must activate successfully')
  const workflowClient = ctx.clientModules.graph().entries.find(entry => entry.id === '@cae/workflow')
  assert.ok(workflowClient, 'workflow must be part of the native client boot graph')
  assert.ok(workflowClient.inject.includes('@deepseek-ai/dsh-client-ui-sidebar-right'))
  const workflowBundle = await ctx.clientModules.fetchBundle({ method: 'GET', url: `http://localhost/${workflowClient.url}` })
  assert.equal(workflowBundle.status, 200)
  assert.match(await workflowBundle.text(), /sidebar.right.pane.tab/)
  const catalog = await ctx.sessionController.modelCatalog()
  assert.deepEqual(catalog.groups, [])
  assert.deepEqual(catalog.failures, [])
  const { sessionId } = await ctx.sessionController.create({})
  assert.ok(sessionId)
  assert.equal(received.length, 0)
})

async function complete(ctx, selection, prepare = false) {
  let text = ''
  let finish
  const options = {
    ...selection,
    messages: [{ role: 'user', content: [{ type: 'text', text: 'smoke test' }] }],
    maxTokens: 16,
    signal: AbortSignal.timeout(10000),
  }
  const prepared = prepare ? await ctx.llm.prepareCall(selection, options.signal) : undefined
  if (prepared) assert.equal(prepared.config.reasoningEffort, 'high')
  const stream = prepared ? prepared.stream({ ...options, ...prepared.config }) : ctx.llm.stream(options)
  for await (const chunk of stream) {
    if (chunk.type === 'text-delta') text += chunk.text
    if (chunk.type === 'finish') finish = chunk.reason
  }
  assert.equal(text, 'configured-ok')
  assert.equal(finish.kind, 'stop')
}

test('saved model is advertised, selected by default and sent through Chat Completions', { timeout: 30000 }, async t => {
  const { ctx, received } = await startModelRuntime(t, 'configured-model')
  const catalog = await ctx.sessionController.modelCatalog()
  assert.deepEqual(catalog.default, { provider: 'cae', model: 'configured-model' })
  assert.deepEqual(catalog.failures, [])
  assert.deepEqual(catalog.groups.map(group => ({
    provider: group.id,
    models: group.models.map(model => model.id),
  })), [{ provider: 'cae', models: ['configured-model'] }])
  assert.equal(catalog.groups[0].models[0].reasoning, undefined)

  await complete(ctx, catalog.default)
  assert.equal(received.length, 1)
  assert.equal(received[0].path, '/v1/chat/completions')
  assert.equal(received[0].authorization, 'Bearer sk-cae-model-test-only')
  assert.equal(received[0].body.model, 'configured-model')
})

test('an unavailable initial model can be replaced while reasoning models retain their own High default', { timeout: 30000 }, async t => {
  const { ctx, received } = await startModelRuntime(t, 'missing-model', ['working-model', 'deepseek-flash', 'deepseek-v4-pro'])
  const catalog = await ctx.sessionController.modelCatalog()
  assert.deepEqual(catalog.groups[0].models.map(model => model.id), ['missing-model', 'working-model', 'deepseek-flash', 'deepseek-v4-pro'])
  assert.equal(catalog.groups[0].models[1].reasoning, undefined)
  assert.deepEqual(catalog.groups[0].models[2].reasoning.efforts.map(effort => effort.id), ['off', 'low', 'high', 'max'])
  assert.equal(catalog.groups[0].models[2].reasoning.defaultEffort, 'high')
  assert.equal(catalog.groups[0].models[3].reasoning.defaultEffort, 'high')

  const { sessionId } = await ctx.sessionController.create({})
  await assert.rejects(complete(ctx, catalog.default))
  assert.equal(received.at(-1).body.model, 'missing-model')
  const { selected } = await ctx.sessionController.selectModel({ sessionId, provider: 'cae', model: 'working-model' })
  await complete(ctx, selected)
  assert.equal(received.at(-1).body.model, 'working-model')
  assert.equal(received.at(-1).body.reasoning_effort, undefined)
  for (const model of ['deepseek-flash', 'deepseek-v4-pro']) {
    const thinking = await ctx.sessionController.selectModel({ sessionId, provider: 'cae', model })
    assert.equal(thinking.selected.reasoningEffort, 'high')
    await complete(ctx, thinking.selected)
    assert.equal(received.at(-1).body.thinking.type, 'enabled')
    assert.equal(received.at(-1).body.reasoning_effort, 'high')

    await complete(ctx, { provider: 'cae', model }, true)
    assert.equal(received.at(-1).body.reasoning_effort, 'high')

    const low = await ctx.sessionController.selectModel({ sessionId, provider: 'cae', model, reasoningEffort: 'low' })
    await complete(ctx, low.selected)
    assert.equal(received.at(-1).body.reasoning_effort, 'low')
    const off = await ctx.sessionController.selectModel({ sessionId, provider: 'cae', model, reasoningEffort: 'off' })
    await complete(ctx, off.selected)
    assert.equal(received.at(-1).body.thinking.type, 'disabled')
    assert.equal(received.at(-1).body.reasoning_effort, undefined)
  }

  const plain = await ctx.sessionController.selectModel({ sessionId, provider: 'cae', model: 'working-model' })
  assert.equal(plain.selected.reasoningEffort, undefined)
  await complete(ctx, plain.selected)
  assert.equal(received.at(-1).body.reasoning_effort, undefined)
})

for (const model of ['deepseek-flash', 'deepseek-v4-pro']) {
  test(`${model} exposes reasoning levels and sends the selected effort`, { timeout: 30000 }, async t => {
    const { ctx, received } = await startModelRuntime(t, model)
    assert.equal((await ctx.llm.resolveModelInfo('cae', model)).context.contextWindow, 1000000)
    const catalog = await ctx.sessionController.modelCatalog()
    assert.deepEqual(catalog.failures, [])
    const reasoning = catalog.groups[0].models[0].reasoning
    assert.deepEqual(reasoning.efforts.map(effort => effort.id), ['off', 'low', 'high', 'max'])
    assert.equal(reasoning.defaultEffort, 'high')

    await complete(ctx, catalog.default)
    assert.equal(received.at(-1).body.thinking.type, 'enabled')
    assert.equal(received.at(-1).body.reasoning_effort, 'high')

    const { sessionId } = await ctx.sessionController.create({})
    for (const reasoningEffort of ['off', 'low', 'high', 'max']) {
      const { selected } = await ctx.sessionController.selectModel({
        sessionId, provider: 'cae', model, reasoningEffort,
      })
      assert.deepEqual(selected, { provider: 'cae', model, reasoningEffort })
      await complete(ctx, selected)
      const { body } = received.at(-1)
      assert.equal(body.model, model)
      assert.equal(body.thinking.type, reasoningEffort === 'off' ? 'disabled' : 'enabled')
      assert.equal(body.reasoning_effort, reasoningEffort === 'off' ? undefined : reasoningEffort)
    }
    assert.equal(received.length, 5)
  })
}

const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { test } = require('node:test')
const { runInNewContext } = require('node:vm')
const { STAGES } = require('../state.cjs')

async function desktop(t, configuration = null) {
  let plugin
  const entries = new Map(), drafts = new Map(), events = [], sent = [], submitted = [], cleanups = []
  const state = { id: 'workflow-id', current: 0, status: 'parameters', revision: 1, parameters: { import: { project_name: 'Current project', igs_file: '/project/current.igs', workdir: '/project' } }, stages: STAGES.map(stage => ({ id: stage.id, status: 'pending', artifacts: [] })), traces: [] }
  const api = {
    load: async () => ({ state, stages: STAGES, configuration, workdir: '/project' }),
    submit: async (...args) => { submitted.push(args); return { ...state, status: configuration ? 'blocked' : 'ready', configuration } },
  }
  const effect = callback => { const dispose = callback(); if (dispose) cleanups.push(dispose) }
  runInNewContext(readFileSync(join(__dirname, '../client.js'), 'utf8'), {
    window: {
      __ModuleLoader__: { load: definition => { plugin = definition.factory(() => ({ createElement: (type, props, ...children) => ({ type, props, children }), useState: initial => [typeof initial === 'function' ? initial() : initial, () => {}], useEffect: effect, useRef: value => ({ current: value }) })) } },
      caeWorkflow: api, caeModels: { load: async () => ({ configured: true }) },
      localStorage: { getItem: key => drafts.get(key), setItem: (key, value) => drafts.set(key, value), removeItem: key => drafts.delete(key) },
      setInterval: () => 1, clearInterval: () => {}, dispatchEvent: event => events.push(event),
    },
    CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options.detail } },
    document: { createElement: () => ({ remove() {} }), head: { appendChild() {} } },
  })
  plugin.apply({
    effect,
    slots: { inject: (_name, register) => register(), register: (options, component) => { entries.set(options.name, component); return () => entries.delete(options.name) } },
    sidebarRight: { openTab: () => {} }, sidebarRightTabs: { register: definition => { assert.equal(definition.kind, 'cae-workflow'); return () => {} } },
    sessions: { scope: id => ({ get: service => { assert.equal(service, 'conversation'); assert.ok(plugin.inject.includes(service)); return { send: async text => sent.push({ id, text }) } } }) },
  })
  t.after(() => cleanups.reverse().forEach(dispose => dispose()))
  const panel = entries.get('sidebar.right.pane.tab')
  panel({ sessionId: 'session' })
  await new Promise(resolve => setImmediate(resolve))
  const tree = panel({ sessionId: 'session' })
  return { tree, sent, submitted, events, state, drafts, entries }
}

function find(tree, predicate) {
  if (!tree || typeof tree !== 'object') return null
  if (predicate(tree)) return tree
  for (const child of (Array.isArray(tree) ? tree : tree.children || [])) { const match = find(child, predicate); if (match) return match }
  return null
}

test('native workflow form sends confirmed parameters to its own conversation with all services declared', async t => {
  const ui = await desktop(t)
  const parameters = find(ui.tree, node => node.type?.name === 'Parameters')
  assert.ok(parameters)
  const form = parameters.type(parameters.props)
  await form.props.onSubmit({ preventDefault() {} })
  // React event handlers intentionally launch the promise without returning it.
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(ui.submitted.length, 1)
  assert.equal(ui.submitted[0][0], 'session')
  assert.equal(ui.submitted[0][2].igs_file, '/project/current.igs')
  assert.equal(ui.sent.length, 1)
  assert.equal(ui.sent[0].id, 'session')
  assert.match(ui.sent[0].text, /cae_workflow begin/)
  assert.ok(ui.entries.has('conversation.input.dock'), 'parameter prompts remain accessible when the native sidebar is collapsed')
})

test('missing HyperMesh opens the existing software settings and retains the input draft', async t => {
  const ui = await desktop(t, { field: 'hmbatch', message: '需要配置 HyperMesh' })
  const parameters = find(ui.tree, node => node.type?.name === 'Parameters')
  const form = parameters.type(parameters.props)
  assert.equal(ui.events[0].type, 'cae:open-simulation-settings')
  assert.equal(ui.events[0].detail.field, 'hmbatch')
  assert.ok([...ui.drafts.values()].some(value => JSON.parse(value).igs_file === '/project/current.igs'))
  form.props.onSubmit({ preventDefault() {} })
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(ui.sent.length, 0)
  assert.equal(ui.submitted.length, 1)
})

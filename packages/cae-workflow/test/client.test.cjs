const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { test } = require('node:test')
const { runInNewContext } = require('node:vm')
const { STAGES } = require('../state.cjs')

async function desktop(t, configuration = null) {
  let plugin
  const entries = new Map(), drafts = new Map(), events = [], sent = [], submitted = [], cleanups = []
  const hookState = new Map(), windowListeners = new Map()
  let owner = '__root__', hookIndex = 0
  const state = { id: 'workflow-id', current: 0, status: 'parameters', revision: 1, parameters: { import: { project_name: 'Current project', igs_file: '/project/current.igs', workdir: '/project' } }, stages: STAGES.map(stage => ({ id: stage.id, status: 'pending', artifacts: [] })), traces: [] }
  const api = {
    load: async () => ({ state, stages: STAGES, configuration, workdir: '/project' }),
    submit: async (...args) => { submitted.push(args); return { ...state, status: configuration ? 'blocked' : 'ready', configuration } },
    preview: async () => 'data:image/png;base64,cHJldmlldw==',
  }
  const effect = callback => { const dispose = callback(); if (dispose) cleanups.push(dispose) }
  const render = (component, props) => {
    owner = component
    hookIndex = 0
    const result = component(props)
    owner = '__root__'
    return result
  }
  runInNewContext(readFileSync(join(__dirname, '../client.js'), 'utf8'), {
    window: {
      __ModuleLoader__: { load: definition => { plugin = definition.factory(() => ({
        createElement: (type, props, ...children) => ({ type, props, children }),
        useState: initial => {
          const index = hookIndex++, slots = hookState.get(owner) || []
          hookState.set(owner, slots)
          if (!(index in slots)) slots[index] = typeof initial === 'function' ? initial() : initial
          return [slots[index], value => { slots[index] = typeof value === 'function' ? value(slots[index]) : value }]
        },
        useEffect: effect,
        useRef: value => ({ current: value }),
      })) } },
      caeWorkflow: api, caeModels: { load: async () => ({ configured: true }) },
      localStorage: { getItem: key => drafts.get(key), setItem: (key, value) => drafts.set(key, value), removeItem: key => drafts.delete(key) },
      setInterval: () => 1, clearInterval: () => {}, dispatchEvent: event => events.push(event),
      addEventListener: (name, callback) => windowListeners.set(name, callback),
      removeEventListener: name => windowListeners.delete(name),
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
  return { tree, sent, submitted, events, state, drafts, entries, render, windowListeners }
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

test('partition previews open an accessible lightbox and close with Escape or the close button', async t => {
  const ui = await desktop(t)
  ui.state.stages[0].artifacts = [{ role: 'preview', path: '/project/partition.png' }]
  const panel = ui.entries.get('sidebar.right.pane.tab')
  const tree = panel({ sessionId: 'session' })
  const artifactsNode = find(tree, node => node.type?.name === 'Artifacts')
  assert.ok(artifactsNode)
  const props = artifactsNode.props
  const artifacts = ui.render(artifactsNode.type, props)
  const previewNode = find(artifacts, node => node.type?.name === 'Preview')
  assert.ok(previewNode)
  ui.render(previewNode.type, previewNode.props)
  await new Promise(resolve => setImmediate(resolve))
  const ready = ui.render(previewNode.type, previewNode.props)
  const trigger = find(ready, node => node.type === 'button' && /放大查看/.test(node.props['aria-label']))
  assert.ok(trigger)
  trigger.props.onClick()
  let expanded = ui.render(artifactsNode.type, props)
  let dialog = find(expanded, node => node.props?.role === 'dialog')
  assert.equal(dialog.props['aria-modal'], 'true')
  assert.ok(find(dialog, node => node.type === 'img'))
  ui.windowListeners.get('keydown')({ key: 'Escape' })
  expanded = ui.render(artifactsNode.type, props)
  assert.equal(find(expanded, node => node.props?.role === 'dialog'), null)
  trigger.props.onClick()
  expanded = ui.render(artifactsNode.type, props)
  dialog = find(expanded, node => node.props?.role === 'dialog')
  find(dialog, node => node.props?.['aria-label'] === '关闭大图').props.onClick()
  assert.equal(find(ui.render(artifactsNode.type, props), node => node.props?.role === 'dialog'), null)
})

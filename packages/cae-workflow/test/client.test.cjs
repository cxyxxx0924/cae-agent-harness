const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { test } = require('node:test')
const { runInNewContext } = require('node:vm')
const { STAGES } = require('../state.cjs')

async function desktop(t, configuration = null) {
  let plugin
  const entries = new Map(), drafts = new Map(), events = [], sent = [], submitted = [], cleanups = []
  const hookState = new Map(), windowListeners = new Map(), sessionListeners = new Set()
  const sessionState = { running: false }
  const session = { getSnapshot: () => sessionState, subscribe: listener => { sessionListeners.add(listener); return () => sessionListeners.delete(listener) } }
  let owner = '__root__', hookIndex = 0
  const state = { id: 'workflow-id', current: 0, status: 'parameters', revision: 1, parameters: { import: { project_name: 'Current project', igs_file: '/project/current.igs', workdir: '/project' } }, stages: STAGES.map(stage => ({ id: stage.id, status: 'pending', artifacts: [] })), traces: [] }
  const api = {
    load: async () => ({ state: structuredClone(state), stages: STAGES, configuration, workdir: '/project' }),
    submit: async (...args) => { submitted.push(args); state.status = configuration ? 'blocked' : 'ready'; state.revision++; return { ...state, configuration } },
    preview: async () => 'data:image/png;base64,cHJldmlldw==',
  }
  const effect = callback => {
    let dispose = callback()
    const cleanup = () => { const current = dispose; dispose = null; current?.() }
    if (dispose) cleanups.push(cleanup)
    return cleanup
  }
  const slotsFor = () => {
    if (!hookState.has(owner)) hookState.set(owner, [])
    return hookState.get(owner)
  }
  const intervals = new Set()
  const conversation = { send: async text => sent.push({ id: 'session', text }) }
  const setRunning = running => { sessionState.running = running; sessionListeners.forEach(listener => listener()) }
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
          const index = hookIndex++, slots = slotsFor()
          if (!(index in slots)) slots[index] = typeof initial === 'function' ? initial() : initial
          return [slots[index], value => { slots[index] = typeof value === 'function' ? value(slots[index]) : value }]
        },
        useEffect: (callback, dependencies) => {
          const index = hookIndex++, slots = slotsFor(), previous = slots[index]
          if (previous && dependencies && dependencies.length === previous.dependencies?.length && dependencies.every((value, i) => Object.is(value, previous.dependencies[i]))) return
          previous?.cleanup()
          slots[index] = { dependencies, cleanup: effect(callback) }
        },
        useRef: value => {
          const index = hookIndex++, slots = slotsFor()
          if (!(index in slots)) slots[index] = { current: value }
          return slots[index]
        },
      })) } },
      caeWorkflow: api, caeModels: { load: async () => ({ configured: true }) },
      localStorage: { getItem: key => drafts.get(key), setItem: (key, value) => drafts.set(key, value), removeItem: key => drafts.delete(key) },
      setInterval: callback => { intervals.add(callback); return callback }, clearInterval: callback => intervals.delete(callback), dispatchEvent: event => events.push(event),
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
    sessions: { binding: () => ({ session }), scope: () => ({ get: service => { assert.equal(service, 'conversation'); assert.ok(plugin.inject.includes(service)); return conversation } }) },
  })
  t.after(() => cleanups.reverse().forEach(dispose => dispose()))
  const panel = entries.get('sidebar.right.pane.tab')
  render(panel, { sessionId: 'session' })
  await new Promise(resolve => setImmediate(resolve))
  const tree = render(panel, { sessionId: 'session' })
  const poll = async () => { intervals.forEach(callback => callback()); await new Promise(resolve => setImmediate(resolve)) }
  const renderPanel = () => render(panel, { sessionId: 'session' })
  const renderForm = (remount = false) => {
    const parameters = find(renderPanel(), node => node.type?.name === 'Parameters')
    if (parameters && remount) {
      hookState.get(parameters.type)?.forEach(slot => slot?.cleanup?.())
      hookState.delete(parameters.type)
    }
    return parameters && render(parameters.type, parameters.props)
  }
  return { tree, sent, submitted, events, state, drafts, entries, render, windowListeners, api, conversation, setRunning, poll, renderPanel, renderForm }
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
  const form = ui.render(parameters.type, parameters.props)
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
  const form = ui.render(parameters.type, parameters.props)
  assert.equal(ui.events[0].type, 'cae:open-simulation-settings')
  assert.equal(ui.events[0].detail.field, 'hmbatch')
  assert.ok([...ui.drafts.values()].some(value => JSON.parse(value).igs_file === '/project/current.igs'))
  form.props.onSubmit({ preventDefault() {} })
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(ui.sent.length, 0)
  assert.equal(ui.submitted.length, 1)
  assert.equal(find(ui.renderForm(), node => node.props?.type === 'submit').props.disabled, false)
})

test('launch stays locked after prompt admission, across polling and form remounts, without duplicate sends', async t => {
  const ui = await desktop(t)
  const form = ui.renderForm()
  form.props.onSubmit({ preventDefault() {} })
  form.props.onSubmit({ preventDefault() {} })
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(ui.submitted.length, 1)
  assert.equal(ui.sent.length, 1)
  assert.equal(ui.state.status, 'ready')

  await ui.poll()
  const pending = ui.renderForm(true)
  const button = find(pending, node => node.props?.type === 'submit')
  assert.equal(button.props.disabled, true)
  assert.equal(button.children[0], '正在启动…')
  assert.equal(find(pending, node => node.type === 'fieldset').props.disabled, true)
  pending.props.onSubmit({ preventDefault() {} })
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(ui.submitted.length, 1)
  assert.equal(ui.sent.length, 1)

  ui.state.status = 'running'
  ui.state.revision++
  await ui.poll()
  assert.equal(ui.renderForm(), null)
  assert.match(JSON.stringify(ui.renderPanel()), /正在执行/)
})

test('the live conversation locks ready forms and releases a launch that ends before begin', async t => {
  const ui = await desktop(t)
  ui.setRunning(true)
  let form = ui.renderForm()
  assert.equal(find(form, node => node.props?.type === 'submit').props.disabled, true)
  assert.equal(find(form, node => node.props?.type === 'submit').children[0], '对话执行中…')
  form.props.onSubmit({ preventDefault() {} })
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(ui.submitted.length, 0)

  ui.setRunning(false)
  form = ui.renderForm()
  form.props.onSubmit({ preventDefault() {} })
  await new Promise(resolve => setImmediate(resolve))
  ui.setRunning(true)
  ui.setRunning(false)
  await new Promise(resolve => setImmediate(resolve))
  form = ui.renderForm()
  assert.equal(find(form, node => node.props?.type === 'submit').props.disabled, false)
  assert.match(JSON.stringify(ui.renderPanel()), /对话已结束，当前阶段尚未开始/)
  form.props.onSubmit({ preventDefault() {} })
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(ui.sent.length, 2)
})

test('a failed send restores the launch button and displays the failure', async t => {
  const ui = await desktop(t)
  ui.conversation.send = async () => { throw new Error('连接已断开，请重试。') }
  ui.renderForm().props.onSubmit({ preventDefault() {} })
  await new Promise(resolve => setImmediate(resolve))
  const form = ui.renderForm()
  assert.equal(find(form, node => node.props?.type === 'submit').props.disabled, false)
  assert.equal(find(form, node => node.props?.type === 'submit').children[0], '继续执行')
  assert.match(JSON.stringify(form), /连接已断开，请重试/)
})

test('a stale in-flight workflow snapshot cannot release a launch lock', async t => {
  const ui = await desktop(t)
  const load = ui.api.load
  const stale = await load()
  let resolveLoad
  ui.api.load = () => new Promise(resolve => { resolveLoad = resolve })
  await ui.poll()
  ui.renderForm().props.onSubmit({ preventDefault() {} })
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(ui.submitted.length, 1)
  assert.equal(ui.sent.length, 0)

  resolveLoad(stale)
  await new Promise(resolve => setImmediate(resolve))
  const pending = ui.renderForm(true)
  assert.equal(ui.sent.length, 1)
  assert.equal(find(pending, node => node.props?.type === 'submit').props.disabled, true)
  pending.props.onSubmit({ preventDefault() {} })
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(ui.submitted.length, 1)

  const current = await load()
  ui.api.load = load
  resolveLoad(current)
  await ui.poll()
  assert.equal(find(ui.renderForm(), node => node.props?.type === 'submit').props.disabled, true)
})

test('partition previews open an accessible lightbox and close with Escape or the close button', async t => {
  const ui = await desktop(t)
  ui.state.stages[0].artifacts = [{ role: 'preview', path: '/project/partition.png' }]
  await ui.poll()
  const panel = ui.entries.get('sidebar.right.pane.tab')
  const tree = ui.render(panel, { sessionId: 'session' })
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

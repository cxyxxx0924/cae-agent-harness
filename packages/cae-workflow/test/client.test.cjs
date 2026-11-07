const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { test } = require('node:test')
const { runInNewContext } = require('node:vm')
const { STAGES } = require('../state.cjs')

async function desktop(t, configuration = null) {
  let plugin
  const entries = new Map(), drafts = new Map(), events = [], sent = [], submitted = [], cleanups = []
  const tabs = [], navigation = [], opened = [], previews = []
  const hookState = new Map(), windowListeners = new Map(), sessionListeners = new Set()
  const sessionState = { running: false }
  const session = { getSnapshot: () => sessionState, subscribe: listener => { sessionListeners.add(listener); return () => sessionListeners.delete(listener) } }
  let owner = '__root__', hookIndex = 0
  const state = { id: 'workflow-id', current: 0, status: 'parameters', revision: 1, parameters: { import: { project_name: 'Current project', igs_file: '/project/current.igs', workdir: '/project' } }, stages: STAGES.map(stage => ({ id: stage.id, status: 'pending', artifacts: [] })), traces: [] }
  const states = new Map([['session', state]])
  const api = {
    load: async (sessionId = 'session') => ({ state: structuredClone(states.get(sessionId) || null), stages: STAGES, configuration, workdir: '/project' }),
    submit: async (...args) => { submitted.push(args); state.status = configuration ? 'blocked' : 'ready'; state.revision++; return { ...state, configuration } },
    open: async (...args) => { opened.push(args) },
    preview: async (...args) => { previews.push(args); return 'data:image/png;base64,cHJldmlldw==' },
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
    slots: { inject: (_name, register) => register(), register: (options, component) => { const key = options.key || options.name; entries.set(key, component); return () => entries.delete(key) } },
    sidebarRight: { openTab: kind => navigation.push(kind) }, sidebarRightTabs: { register: definition => { tabs.push(definition); return () => {} } },
    sessions: { binding: () => ({ session }), scope: () => ({ get: service => { assert.equal(service, 'conversation'); assert.ok(plugin.inject.includes(service)); return conversation } }) },
  })
  t.after(() => cleanups.reverse().forEach(dispose => dispose()))
  const panel = entries.get('@cae/workflow')
  render(panel, { sessionId: 'session' })
  await new Promise(resolve => setImmediate(resolve))
  const tree = render(panel, { sessionId: 'session' })
  const poll = async () => { intervals.forEach(callback => callback()); await new Promise(resolve => setImmediate(resolve)) }
  const renderPanel = () => render(panel, { sessionId: 'session' })
  const renderResults = async (sessionId = 'session') => {
    const component = entries.get('@cae/workflow-results')
    render(component, { sessionId })
    await new Promise(resolve => setImmediate(resolve))
    const tree = render(component, { sessionId })
    const files = find(tree, node => node.type?.name === 'ResultFiles')
    return files ? render(files.type, files.props) : tree
  }
  const renderForm = (remount = false) => {
    const parameters = find(renderPanel(), node => node.type?.name === 'Parameters')
    if (parameters && remount) {
      hookState.get(parameters.type)?.forEach(slot => slot?.cleanup?.())
      hookState.delete(parameters.type)
    }
    return parameters && render(parameters.type, parameters.props)
  }
  return { tree, sent, submitted, events, state, states, drafts, entries, tabs, navigation, opened, previews, render, windowListeners, api, conversation, setRunning, poll, renderPanel, renderForm, renderResults }
}

function find(tree, predicate) {
  if (!tree || typeof tree !== 'object') return null
  if (predicate(tree)) return tree
  for (const child of (Array.isArray(tree) ? tree : tree.children || [])) { const match = find(child, predicate); if (match) return match }
  return null
}

function findAll(tree, predicate) {
  if (!tree || typeof tree !== 'object') return []
  return [...(predicate(tree) ? [tree] : []), ...(Array.isArray(tree) ? tree : tree.children || []).flatMap(child => findAll(child, predicate))]
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
  const panel = ui.entries.get('@cae/workflow')
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

test('mesh result review displays accepted warnings before user confirmation', async t => {
  const ui = await desktop(t)
  ui.state.current = 2
  ui.state.status = 'review'
  ui.state.stages[2].warnings = [{ name: '拓扑门禁', summary: 'Short edges retained', detail: [['最小边 <3mm', { 2: 8, 3: 8 }, 'WARN']] }]
  await ui.poll()
  const component = find(ui.renderPanel(), node => node.type?.name === 'Review')
  const tree = ui.render(component.type, component.props)
  const warning = find(tree, node => node.props?.role === 'status')
  assert.match(JSON.stringify(warning), /Short edges retained/)
  assert.match(JSON.stringify(warning), /最小边 <3mm/)
  assert.ok(find(tree, node => node.type === 'button' && JSON.stringify(node.children).includes('确认结果')))
})

test('result files have native sidebar, workflow and conversation entries, including after completion', async t => {
  const ui = await desktop(t)
  assert.deepEqual(ui.tabs.map(tab => tab.kind), ['cae-workflow', 'cae-results'])
  assert.equal(ui.tabs[1].title(), '结果文件')
  find(ui.renderPanel(), node => node.props?.className === 'cae-flow-files-entry').props.onClick()
  assert.equal(ui.navigation.at(-1), 'cae-results')

  ui.state.status = 'completed'
  ui.state.stages[0].artifacts = [{ role: 'geometry', path: 'C:\\project\\geometry.hm', remote: false }]
  await ui.poll()
  const header = ui.render(ui.entries.get('conversation.session.header.utilities'), { sessionId: 'session' })
  const entry = find(header, node => node.type === 'button' && node.children[0] === '结果文件 · 1')
  assert.ok(entry)
  entry.props.onClick()
  assert.equal(ui.navigation.at(-1), 'cae-results')
  const panel = ui.render(ui.entries.get('@cae/workflow-results'), { sessionId: 'session' })
  find(panel, node => node.props?.className === 'cae-flow-results-back').props.onClick()
  assert.equal(ui.navigation.at(-1), 'cae-workflow')
})

test('results accumulate across stages, deduplicate paths, filter and update with workflow polling', async t => {
  const ui = await desktop(t)
  ui.state.current = 3
  ui.state.status = 'running'
  ui.state.stages[0].artifacts = [{ role: 'geometry', path: 'C:\\project\\geometry.hm', remote: false }]
  ui.state.stages[1].artifacts = [
    { role: 'partitioned_model', path: 'C:\\project\\partition.hm', remote: false },
    { role: 'preview', path: 'C:\\project\\partition.png', remote: false },
  ]
  ui.state.stages[2].artifacts = [
    { role: 'mesh_model', path: 'C:\\project\\partition.hm', remote: false },
    { role: 'curtain_k', path: '/project/curtain.k', remote: false },
  ]
  await ui.poll()
  let results = await ui.renderResults()
  let rows = findAll(results, node => node.props?.className === 'cae-flow-file')
  assert.equal(rows.length, 4)
  const shared = rows.find(node => JSON.stringify(node).includes('partition.hm'))
  assert.match(JSON.stringify(shared), /四分区模型 \/ 网格模型/)
  assert.ok(JSON.stringify(shared).includes(STAGES[1].title))
  assert.ok(JSON.stringify(shared).includes(STAGES[2].title))
  assert.ok(find(rows[0], node => node.type === 'strong' && node.children[0] === 'geometry.hm'), 'Windows file names do not include the directory')

  find(results, node => node.props?.['aria-label'] === '按阶段筛选结果文件').props.onChange({ target: { value: STAGES[2].id } })
  results = await ui.renderResults()
  assert.equal(findAll(results, node => node.props?.className === 'cae-flow-file').length, 2)
  find(results, node => node.props?.['aria-label'] === '搜索结果文件').props.onChange({ target: { value: 'CURTAIN.K' } })
  results = await ui.renderResults()
  assert.equal(findAll(results, node => node.props?.className === 'cae-flow-file').length, 1)

  find(results, node => node.props?.['aria-label'] === '搜索结果文件').props.onChange({ target: { value: 'missing-file' } })
  results = await ui.renderResults()
  assert.match(JSON.stringify(results), /没有匹配的文件/)
  find(results, node => node.type === 'button' && node.children[0] === '清除筛选').props.onClick()
  ui.state.stages[3].artifacts = [{ role: 'd3plot', path: '/server/results/d3plot', remote: true }]
  ui.state.current = 4
  await ui.poll()
  results = await ui.renderResults()
  rows = findAll(results, node => node.props?.className === 'cae-flow-file')
  assert.equal(rows.length, 5)
  const remote = rows.find(node => JSON.stringify(node).includes('/server/results/d3plot'))
  assert.ok(find(remote, node => node.props?.className === 'cae-flow-file-type' && node.children[0] === 'D3PLOT'))
  assert.match(JSON.stringify(remote), /服务端文件，请同步到本机后查看/)
  assert.equal(find(remote, node => node.type === 'button'), null)
})

test('results open local files and preview images with recoverable file errors', async t => {
  const ui = await desktop(t)
  ui.state.stages[0].artifacts = [{ role: 'preview', path: '/project/partition.png', remote: false }]
  await ui.poll()
  let results = await ui.renderResults()
  find(results, node => node.props?.['aria-label'] === '打开 partition.png').props.onClick()
  await new Promise(resolve => setImmediate(resolve))
  assert.deepEqual(Array.from(ui.opened[0]), ['session', '/project/partition.png'])

  results = await ui.renderResults()
  find(results, node => node.props?.['aria-label'] === '预览 partition.png').props.onClick()
  await new Promise(resolve => setImmediate(resolve))
  results = await ui.renderResults()
  assert.deepEqual(Array.from(ui.previews[0]), ['session', '/project/partition.png'])
  const dialog = find(results, node => node.props?.role === 'dialog')
  assert.equal(dialog.props['aria-label'], 'partition.png')
  assert.equal(find(dialog, node => node.type === 'img').props.src, 'data:image/png;base64,cHJldmlldw==')
  ui.windowListeners.get('keydown')({ key: 'Escape' })
  assert.equal(find(await ui.renderResults(), node => node.props?.role === 'dialog'), null)

  ui.api.open = async () => { throw new Error('文件已移动') }
  results = await ui.renderResults()
  find(results, node => node.props?.['aria-label'] === '打开 partition.png').props.onClick()
  await new Promise(resolve => setImmediate(resolve))
  results = await ui.renderResults()
  assert.match(JSON.stringify(find(results, node => node.props?.role === 'alert')), /partition.png：文件已移动/)
  ui.api.open = async () => {}
  find(results, node => node.props?.['aria-label'] === '打开 partition.png').props.onClick()
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(find(await ui.renderResults(), node => node.props?.role === 'alert'), null)
})

test('results show empty states and do not expose the previous conversation while switching sessions', async t => {
  const ui = await desktop(t)
  assert.match(JSON.stringify(await ui.renderResults()), /暂无结果文件/)
  ui.state.stages[0].artifacts = [{ role: 'geometry', path: '/project/private.hm', remote: false }]
  await ui.poll()
  assert.match(JSON.stringify(await ui.renderResults()), /private.hm/)
  const resultsPanel = ui.entries.get('@cae/workflow-results')
  const switching = ui.render(resultsPanel, { sessionId: 'other-session' })
  assert.match(JSON.stringify(switching), /正在读取结果文件/)
  assert.doesNotMatch(JSON.stringify(switching), /Current project|private.hm/)
  const empty = await ui.renderResults('other-session')
  assert.match(JSON.stringify(empty), /当前对话还没有仿真工作流/)
  assert.doesNotMatch(JSON.stringify(empty), /private.hm/)
  assert.match(JSON.stringify(await ui.renderResults()), /private.hm/)
})

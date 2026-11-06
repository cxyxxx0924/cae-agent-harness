const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { resolve } = require('node:path')
const { test } = require('node:test')
const { runInNewContext } = require('node:vm')

async function desktop(configured) {
  let plugin
  let openFromMenu
  const openedSections = []
  const started = []
  const cleanups = []
  const blocks = new Map()
  const entries = new Map([
    ['sidebar.settings', [{ store: { create: () => ({ actions: { openSection: id => openedSections.push(id) } }) } }]],
    ['conversation.input.model', [{ options: { priority: 0 }, component: () => 'normal-model-picker' }]],
  ])
  const slots = {
    entries: name => entries.get(name) ?? [],
    inject: (_name, register) => {
      const dispose = register()
      if (dispose) cleanups.push(dispose)
    },
    register: (options, component) => {
      const seat = { options, component }
      entries.set(options.name, [...slots.entries(options.name), seat])
      return () => entries.set(options.name, slots.entries(options.name).filter(entry => entry !== seat))
    },
  }
  const navigation = { startSession: (...args) => started.push(args) }
  const originalStart = navigation.startSession
  const effect = callback => {
    const dispose = callback()
    if (dispose) cleanups.push(dispose)
  }
  runInNewContext(readFileSync(resolve(__dirname, '../../cae-ui/client.js'), 'utf8'), {
    window: {
      __ModuleLoader__: { load: definition => {
        plugin = definition.factory(name => {
          assert.equal(name, 'react')
          return {
            createElement: (type, props, ...children) => ({ type, props, children }),
            useEffect: effect,
          }
        })
      } },
      caeModels: {
        load: async () => ({ configured }),
        onOpenSettings: callback => {
          openFromMenu = callback
          return () => { openFromMenu = undefined }
        },
      },
    },
    document: { createElement: () => ({ remove() {} }), head: { appendChild() {} } },
  })
  const services = {
    slots,
    conversation: { blocks: {
      set: (id, value) => blocks.set(id, value),
      storeFor: id => ({ getSnapshot: () => blocks.get(id) }),
    } },
  }
  plugin.apply(new Proxy({
    effect,
    inject: (names, callback) => {
      assert.deepEqual(Array.from(names), ['uiWorkspace'])
      callback({ uiWorkspace: navigation, effect })
    },
  }, {
    get(target, key) {
      if (key in services) {
        assert.ok(plugin.inject.includes(key), `${key} must be declared as an injected service`)
        return services[key]
      }
      return target[key]
    },
  }))
  await new Promise(resolve => setImmediate(resolve))
  const render = (name, props = {}) => {
    const entry = [...slots.entries(name)].sort((left, right) => (left.options.priority ?? 0) - (right.options.priority ?? 0))[0]
    return entry.component(props)
  }
  return { navigation, originalStart, render, openedSections, started, blocks,
    openMenu: () => openFromMenu(),
    dispose: () => cleanups.reverse().forEach(cleanup => cleanup()),
  }
}

test('unconfigured desktop opens settings on model/new-session actions while initial browsing stays open', async t => {
  const ui = await desktop(false)
  t.after(ui.dispose)
  assert.equal(ui.openedSections.length, 0)
  assert.equal(ui.started.length, 0)
  const model = ui.render('conversation.input.model', { sessionId: 'existing-session', locked: false })
  assert.equal(model.type, 'button')
  assert.equal(model.props['aria-label'], '选择模型')
  assert.equal(ui.blocks.get('existing-session').reason, '请先选择模型并完成配置')
  model.props.onClick()
  ui.navigation.startSession('workspace-from-pointer')
  ui.navigation.startSession()
  await new Promise(resolve => setImmediate(resolve))
  assert.deepEqual(ui.openedSections, ['cae-models', 'cae-models', 'cae-models'])
  assert.equal(ui.started.length, 0)
  const hero = ui.render('conversation.hero.agentPreset', {})
  assert.equal(hero.type({}).props['aria-label'], '选择模型')
  assert.equal(ui.render('conversation.hero.agentPreset', { sessionId: 'existing-session' }), null)
  ui.openMenu()
  assert.equal(ui.openedSections.at(-1), 'cae-models')
})

test('configured desktop keeps normal model selection and passes the new-session request through', async t => {
  const ui = await desktop(true)
  t.after(ui.dispose)
  assert.equal(ui.openedSections.length, 0)
  assert.equal(ui.render('conversation.input.model'), 'normal-model-picker')
  const options = { prompt: 'existing draft', clearPreviousDraft: false }
  ui.navigation.startSession('workspace', options)
  await new Promise(resolve => setImmediate(resolve))
  assert.deepEqual(ui.started, [['workspace', options]])
  assert.equal(ui.openedSections.length, 0)
  ui.openMenu()
  assert.deepEqual(ui.openedSections, ['cae-models'])
})

test('onboarding teardown restores navigation and releases the composer block it owns', async () => {
  const ui = await desktop(false)
  ui.render('conversation.input.model', { sessionId: 'existing-session' })
  ui.dispose()
  assert.equal(ui.navigation.startSession, ui.originalStart)
  assert.equal(ui.blocks.get('existing-session'), undefined)
  assert.equal(ui.render('conversation.input.model'), 'normal-model-picker')
})

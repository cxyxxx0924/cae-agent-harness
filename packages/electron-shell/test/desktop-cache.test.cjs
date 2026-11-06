const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { resolve } = require('node:path')
const { test } = require('node:test')
const { runInNewContext } = require('node:vm')
const { clearDesktopCache } = require('../dist/desktop-cache.js')

test('cache cleanup targets offline resources and leaves authentication and persistent UI data intact', async () => {
  const data = new Map([
    ['cookies', 'session-cookie'], ['localstorage', 'preferences-and-draft'],
    ['indexdb', 'persistent-data'], ['serviceworkers', 'old-worker'], ['cachestorage', 'old-bundle'],
  ])
  let httpCache = 'old-http-bundle'
  let codeCache = 'old-compiled-script'
  await clearDesktopCache({
    clearStorageData: async options => {
      assert.equal(options.origin, 'http://127.0.0.1:3080')
      assert.ok(options.storages?.length, 'must never clear every storage type by default')
      for (const storage of options.storages) data.delete(storage)
    },
    clearCache: async () => { httpCache = null },
    clearCodeCaches: async () => { codeCache = null },
  }, 'http://127.0.0.1:3080')
  assert.deepEqual(Object.fromEntries(data), {
    cookies: 'session-cookie', localstorage: 'preferences-and-draft', indexdb: 'persistent-data',
  })
  assert.equal(httpCache, null)
  assert.equal(codeCache, null)
})

test('cache cleanup reports a failure instead of claiming success', async () => {
  await assert.rejects(clearDesktopCache({
    clearStorageData: async () => {},
    clearCache: async () => { throw new Error('cache is locked') },
    clearCodeCaches: async () => {},
  }, 'http://127.0.0.1:3080'), /cache is locked/)
})

function cachePage(api) {
  let plugin
  let cursor = 0
  const state = []
  const sections = []
  runInNewContext(readFileSync(resolve(__dirname, '../../cae-ui/client.js'), 'utf8'), {
    Error,
    window: {
      caeDesktop: api,
      __ModuleLoader__: { load: definition => {
        plugin = definition.factory(() => ({
          createElement: (type, props, ...children) => ({ type, props, children }),
          useEffect: () => {},
          useState: initial => {
            const index = cursor++
            if (!(index in state)) state[index] = initial
            return [state[index], value => { state[index] = value }]
          },
        }))
      } },
    },
    document: { createElement: () => ({}), head: { appendChild() {} } },
  })
  plugin.apply({
    effect: callback => callback(),
    slots: {
      inject: (_name, callback) => callback(),
      register: (options, component) => sections.push({ ...options, component }),
    },
  })
  return {
    sections,
    render: () => {
      cursor = 0
      return sections.find(section => section.id === 'cae-cache').component()
    },
  }
}

function nodes(tree) {
  if (!tree || typeof tree !== 'object') return []
  return [tree, ...tree.children.flatMap(nodes)]
}

test('model settings stay visible when the desktop bridge is unavailable and explain how to recover', () => {
  const ui = cachePage(undefined)
  const modelPage = ui.sections.find(section => section.id === 'cae-models').component()
  assert.match(JSON.stringify(modelPage), /视图 → 清除缓存并刷新/)
  assert.equal(nodes(ui.render()).some(node => node.type === 'button'), false)
})

test('the cache page waits for confirmation/cleanup and returns to idle on cancellation', async () => {
  let finish
  const ui = cachePage({ clearCache: () => new Promise(resolve => { finish = resolve }) })
  nodes(ui.render()).find(node => node.type === 'button').props.onClick()
  const pendingButton = nodes(ui.render()).find(node => node.type === 'button')
  assert.equal(pendingButton.props.disabled, true)
  finish(false)
  await new Promise(resolve => setImmediate(resolve))
  const result = nodes(ui.render())
  assert.equal(result.find(node => node.type === 'button').props.disabled, false)
  assert.equal(result.find(node => node.props?.className === 'cae-settings-message').children[0], '')
})

test('the cache page shows failures and allows retry', async () => {
  const ui = cachePage({ clearCache: async () => { throw new Error('cache is locked') } })
  nodes(ui.render()).find(node => node.type === 'button').props.onClick()
  await new Promise(resolve => setImmediate(resolve))
  const result = nodes(ui.render())
  assert.equal(result.find(node => node.type === 'button').props.disabled, false)
  assert.equal(result.find(node => node.props?.role === 'alert').children[0], 'cache is locked')
})

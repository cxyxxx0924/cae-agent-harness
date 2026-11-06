const assert = require('node:assert/strict')
const { EventEmitter } = require('node:events')
const { readFileSync } = require('node:fs')
const { createRequire } = require('node:module')
const { resolve } = require('node:path')
const { Script } = require('node:vm')
const { test } = require('node:test')

function editing() {
  const filename = resolve(__dirname, '../dist/native-editing.js')
  const requireFromFile = createRequire(filename)
  const module = { exports: {} }
  const menus = []
  const load = new Script(`(function(require, module, exports) { ${readFileSync(filename, 'utf8')}\n})`, { filename }).runInThisContext()
  load(name => name === 'electron' ? { Menu: { buildFromTemplate: template => ({
    popup: options => menus.push({ template, ...options }),
  }) } } : requireFromFile(name), module, module.exports)
  const win = { webContents: new EventEmitter() }
  module.exports.enableEditingContextMenu(win)
  return { win, menus, EDIT_MENU: module.exports.EDIT_MENU }
}

test('the native Edit menu supplies platform editing shortcuts through Electron roles', () => {
  const { EDIT_MENU } = editing()
  assert.deepEqual(EDIT_MENU.submenu.filter(item => item.role).map(item => item.role), [
    'undo', 'redo', 'cut', 'copy', 'paste', 'selectAll',
  ])
})

test('input context menus use Chromium edit permissions and target their owning window', () => {
  const { win, menus } = editing()
  const editFlags = { canUndo: true, canRedo: false, canCut: false, canCopy: false, canPaste: true, canSelectAll: true }
  win.webContents.emit('context-menu', {}, { isEditable: true, selectionText: '', editFlags })
  assert.equal(menus.length, 1)
  assert.equal(menus[0].window, win)
  const items = Object.fromEntries(menus[0].template.filter(item => item.role).map(item => [item.role, item.enabled]))
  assert.deepEqual(items, { undo: true, redo: false, cut: false, copy: false, paste: true, selectAll: true })
})

test('noneditable pages only offer Copy for a copyable selection', () => {
  const { win, menus } = editing()
  win.webContents.emit('context-menu', {}, { isEditable: false, selectionText: '', editFlags: { canCopy: false } })
  win.webContents.emit('context-menu', {}, { isEditable: false, selectionText: 'protected', editFlags: { canCopy: false } })
  assert.equal(menus.length, 0)
  win.webContents.emit('context-menu', {}, { isEditable: false, selectionText: 'help text', editFlags: { canCopy: true } })
  assert.equal(menus.length, 1)
  assert.deepEqual(menus[0].template.map(item => item.role), ['copy'])
})

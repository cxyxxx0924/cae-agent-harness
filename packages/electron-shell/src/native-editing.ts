import { Menu, type BrowserWindow, type MenuItemConstructorOptions } from 'electron'

export const EDIT_MENU: MenuItemConstructorOptions = {
  label: '编辑',
  submenu: [
    { role: 'undo', label: '撤销' },
    { role: 'redo', label: '重做' },
    { type: 'separator' },
    { role: 'cut', label: '剪切' },
    { role: 'copy', label: '复制' },
    { role: 'paste', label: '粘贴' },
    { type: 'separator' },
    { role: 'selectAll', label: '全选' },
  ],
}

export function enableEditingContextMenu(win: BrowserWindow): void {
  win.webContents.on('context-menu', (_event, params) => {
    const { editFlags, isEditable, selectionText } = params
    const template: MenuItemConstructorOptions[] = []
    if (isEditable) {
      template.push(
        { role: 'undo', label: '撤销', enabled: editFlags.canUndo },
        { role: 'redo', label: '重做', enabled: editFlags.canRedo },
        { type: 'separator' },
        { role: 'cut', label: '剪切', enabled: editFlags.canCut },
        { role: 'copy', label: '复制', enabled: editFlags.canCopy },
        { role: 'paste', label: '粘贴', enabled: editFlags.canPaste },
        { type: 'separator' },
        { role: 'selectAll', label: '全选', enabled: editFlags.canSelectAll },
      )
    } else if (selectionText && editFlags.canCopy) {
      template.push({ role: 'copy', label: '复制' })
    }
    if (template.length) Menu.buildFromTemplate(template).popup({ window: win })
  })
}

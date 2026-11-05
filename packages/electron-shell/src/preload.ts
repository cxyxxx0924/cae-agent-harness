import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('caeSettings', {
  load: () =>
    ipcRenderer.invoke('settings:load'),

  save: (s: unknown) =>
    ipcRenderer.invoke('settings:save', s),

  browseExe: (title: string) =>
    ipcRenderer.invoke('settings:browse-exe', title),

  browseDir: (title: string) =>
    ipcRenderer.invoke('settings:browse-dir', title),

  checkPaths: (paths: Record<string, string>) =>
    ipcRenderer.invoke('settings:check-paths', paths),

  checkService: (settings: unknown) =>
    ipcRenderer.invoke('settings:check-service', settings),

  onSaved: (cb: () => void) => {
    ipcRenderer.on('settings:saved', () => cb())
  },
})

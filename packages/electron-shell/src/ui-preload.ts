import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('caeDesktop', {
  clearCache: () => ipcRenderer.invoke('desktop:clear-cache'),
})

contextBridge.exposeInMainWorld('caeModels', {
  load: () => ipcRenderer.invoke('models:load'),
  save: (settings: unknown) => ipcRenderer.invoke('models:save', settings),
  discover: (settings: unknown) => ipcRenderer.invoke('models:discover', settings),
  test: (settings: unknown) => ipcRenderer.invoke('models:test', settings),
  onOpenSettings: (callback: () => void) => {
    const listener = () => callback()
    ipcRenderer.on('models:open-settings', listener)
    return () => ipcRenderer.removeListener('models:open-settings', listener)
  },
})

contextBridge.exposeInMainWorld('caeSimulation', {
  load: () => ipcRenderer.invoke('simulation:load'),
  save: (settings: unknown) => ipcRenderer.invoke('simulation:save', settings),
  browse: (kind: string, title: string) => ipcRenderer.invoke('simulation:browse', kind, title),
  checkPaths: (paths: unknown) => ipcRenderer.invoke('simulation:check-paths', paths),
  checkService: (settings: unknown) => ipcRenderer.invoke('simulation:check-service', settings),
})

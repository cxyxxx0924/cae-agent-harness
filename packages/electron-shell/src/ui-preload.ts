import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('caeSimulation', {
  load: () => ipcRenderer.invoke('simulation:load'),
  save: (settings: unknown) => ipcRenderer.invoke('simulation:save', settings),
  browse: (kind: string, title: string) => ipcRenderer.invoke('simulation:browse', kind, title),
  checkPaths: (paths: unknown) => ipcRenderer.invoke('simulation:check-paths', paths),
})

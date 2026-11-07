import { app, BrowserWindow, shell, Menu, dialog } from 'electron'
import { ipcMain } from 'electron'
import { spawn, type ChildProcess } from 'node:child_process'
import { resolve, join, delimiter } from 'node:path'
import { existsSync, statSync } from 'node:fs'
import { checkDshPort, waitForDsh } from './dsh-startup'
import { RuntimeLog } from './runtime-log'
import { EDIT_MENU, enableEditingContextMenu } from './native-editing'
import { clearDesktopCache } from './desktop-cache'
import { loadSettings, saveSettings, saveSimulationSettings, type CaeSettings } from './store'
import { discoverModels, modelEnvironment, parseModelConfiguration, testModels } from './model-settings'
import { SIMULATION_FIELDS, SIMULATION_PATH_FIELDS, parseSimulationSettings, simulationEnvironment, checkSolverService } from './simulation-settings'
import { workflowArtifact, workflowPreview, workflowField } from './workflow'
import {
  preparePythonMcpEnvironments,
  pythonMcpFeatureEnvironment,
  stopPythonMcpPreparations,
  uvEnvironment,
} from './python-mcp'

// ── Constants ─────────────────────────────────────────────────────────────
const DSH_PORT          = Number(process.env.DSH_PORT ?? 3080)
const DSH_URL           = `http://127.0.0.1:${DSH_PORT}`
const STARTUP_TIMEOUT_MS = 60_000
const IS_PACKAGED       = app.isPackaged
const APP_NAME = 'SIMFLOW'
const USER_DATA_PATH = app.getPath('userData')
app.setName(APP_NAME)
app.setPath('userData', USER_DATA_PATH)

// ── Paths ──────────────────────────────────────────────────────────────────
function resourcePath(...parts: string[]): string {
  return IS_PACKAGED
    ? join(process.resourcesPath, 'runtime', ...parts)
    : resolve(__dirname, '../../..', ...parts)
}

const { WorkflowStore, STAGES, missingSoftware }: typeof import('../../cae-workflow/state.cjs') = require(resourcePath('packages', 'cae-workflow', 'state.cjs'))

function dshBin(): string {
  const candidates = [
    resourcePath('node_modules', '@deepseek-ai', 'dsh', 'lib', 'bin.js'),
    join(__dirname, '../../node_modules/@deepseek-ai/dsh/lib/bin.js'),
    join(__dirname, '../../../node_modules/@deepseek-ai/dsh/lib/bin.js'),
    resolve(__dirname, '../../../node_modules/.bin/dsh'),
  ]
  for (const c of candidates) {
    if (existsSync(c)) return c
  }
  throw new Error('Cannot locate @deepseek-ai/dsh binary. Run pnpm install first.')
}

function projectRoot(): string {
  return resourcePath()
}

function profilePath(): string {
  return resourcePath('config', 'cae-airbag.cordis.yml')
}

// ── State ──────────────────────────────────────────────────────────────────
let dshProcess:    ChildProcess | null  = null
let dshUrl: string | null = null
let startupComplete = false
let dshRestart: Promise<void> | null = null
let cacheClear: Promise<boolean> | null = null
let mainWindow:    BrowserWindow | null = null
let launchingDsh = false
let quitting = false
let runtimeLog: RuntimeLog
const workflowStore = () => new WorkflowStore(join(app.getPath('userData'), 'workflows'))

// ── dsh lifecycle ─────────────────────────────────────────────────────────
function spawnDsh(settings: CaeSettings): ChildProcess {
  const modelEnv = modelEnvironment(settings)
  const simulationSettings = parseSimulationSettings(settings)
  const simulationEnv = simulationEnvironment(simulationSettings)
  const pythonMcpEnv = pythonMcpFeatureEnvironment(simulationSettings)
  const bin     = dshBin()
  const profile = profilePath()
  runtimeLog.setSecrets([settings.apiKey, simulationSettings.solverServerToken, simulationSettings.solverLocalServiceToken])
  const env: NodeJS.ProcessEnv = {
    ...process.env,
    ELECTRON_RUN_AS_NODE: '1',
    DSH_PORT:           String(DSH_PORT),
    DSH_NO_OPEN_BROWSER: '1',
    CAE_DESKTOP:        '1',
    CAE_WORKFLOW_DIR:   join(app.getPath('userData'), 'workflows'),
    CAE_PROJECT_ROOT:   projectRoot(),
    // Saved desktop settings take precedence over the launch environment.
    ...modelEnv,
    ...simulationEnv,
    ...pythonMcpEnv,
  }
  const nodeExecutable = IS_PACKAGED ? resourcePath('node', 'node.exe') : 'node'
  if (IS_PACKAGED) {
    if (!existsSync(nodeExecutable)) throw new Error('应用缺少 Node.js 运行环境，请重新完整解压应用。')
    const inheritedPath = Object.entries(env).find(([key]) => key.toLowerCase() === 'path')?.[1] ?? ''
    for (const key of Object.keys(env)) {
      if (key.toLowerCase() === 'path') delete env[key]
    }
    env.PATH = [resourcePath('node'), resourcePath('uv'), inheritedPath].join(delimiter)
    env.UV_CACHE_DIR = join(app.getPath('userData'), 'uv-cache')
    env.CAE_UV_INDEX_URL = process.env.CAE_UV_INDEX_URL || process.env.UV_INDEX_URL || ''
  }
  // Remove empty-string entries to avoid overriding child-process defaults
  for (const key of Object.keys(env)) {
    if (env[key] === '' && !(key in simulationEnv) && !(key in modelEnv)) delete env[key]
  }
  const uvEnv = uvEnvironment(env, IS_PACKAGED && process.platform === 'win32')
  runtimeLog.write('main', `Starting dsh: node=${nodeExecutable}; cwd=${projectRoot()}; profile=${profile}; port=${DSH_PORT}`)
  const proc = spawn(nodeExecutable, [bin, 'web', '--patch', profile, '--no-open', '--host', '127.0.0.1', '--port', String(DSH_PORT)], {
    env: uvEnv,
    cwd: projectRoot(),
    stdio: ['ignore', process.platform === 'win32' ? 'overlapped' : 'pipe', process.platform === 'win32' ? 'overlapped' : 'pipe'],
    detached: false,
    shell: false,
    windowsHide: true,
  })
  runtimeLog.capture(proc)
  proc.once('spawn', () => runtimeLog.write('main', `dsh spawned (pid=${proc.pid})`))
  const uvExecutable = IS_PACKAGED
    ? join(resourcePath('uv'), process.platform === 'win32' ? 'uv.exe' : 'uv')
    : 'uv'
  preparePythonMcpEnvironments(
    simulationSettings,
    projectRoot(),
    uvExecutable,
    uvEnv,
  )
  proc.on('error', (error) => {
    runtimeLog.write('main', error.message)
  })
  proc.on('exit', (code) => {
    runtimeLog.write('main', `dsh exited with code ${code}`)
    if (dshProcess !== proc) return
    dshProcess = null
    dshUrl = null
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow
        .loadFile(join(__dirname, '..', 'resources', 'error.html'))
        .catch(() => { /* ignore */ })
    }
  })
  return proc
}

async function stopDsh(): Promise<void> {
  const proc = dshProcess
  dshProcess = null
  dshUrl = null
  if (!proc?.pid || proc.exitCode !== null || proc.signalCode !== null) return
  await new Promise<void>((resolve, reject) => {
    const timeout = setTimeout(() => proc.kill('SIGKILL'), 3000)
    proc.once('exit', () => {
      clearTimeout(timeout)
      proc.off('error', onError)
      resolve()
    })
    function onError(error: Error): void {
      clearTimeout(timeout)
      reject(error)
    }
    proc.once('error', onError)
    proc.kill('SIGTERM')
  })
}

async function startDsh(): Promise<void> {
  await checkDshPort(DSH_PORT)
  if (quitting) return
  dshProcess = spawnDsh(loadSettings())
  try {
    dshUrl = await waitForDsh(dshProcess, DSH_URL, STARTUP_TIMEOUT_MS)
    runtimeLog.write('main', 'dsh authentication succeeded; opening chat')
  } catch (error) {
    runtimeLog.write('main', error instanceof Error ? error.message : String(error))
    await stopDsh()
    throw error
  }
}

async function restartDsh(): Promise<void> {
  if (dshRestart) return dshRestart
  dshRestart = (async () => {
    await stopDsh()
    await startDsh()
    if (quitting) return
    if (mainWindow && !mainWindow.isDestroyed()) {
      await mainWindow.loadURL(dshUrl!)
    }
  })()
  try {
    await dshRestart
  } finally {
    dshRestart = null
  }
}

async function clearCacheAndReload(): Promise<boolean> {
  if (cacheClear) return cacheClear
  if (dshRestart || !dshUrl) throw new Error('后台服务正在启动或重启，请稍后重试。')
  const win = mainWindow
  if (!win || win.isDestroyed()) throw new Error('主窗口已关闭，请重新打开应用。')
  cacheClear = (async () => {
    const { response } = await dialog.showMessageBox(win, {
      type: 'question',
      title: '清除缓存',
      message: '清除界面缓存并刷新应用？',
      detail: '用于修复设置入口缺失、界面显示异常等问题。未保存的输入会丢失；已保存的模型配置、仿真软件设置、对话记录和文件会保留。',
      buttons: ['取消', '清除并刷新'],
      defaultId: 0,
      cancelId: 0,
      noLink: true,
    })
    if (response !== 1) return false
    await clearDesktopCache(win.webContents.session, DSH_URL)
    if (!win.isDestroyed()) await win.loadURL(dshUrl!)
    runtimeLog.write('main', 'Desktop UI cache cleared; reloaded chat')
    return true
  })()
  try {
    return await cacheClear
  } finally {
    cacheClear = null
  }
}

// ── IPC handlers ───────────────────────────────────────────────────────────
function registerIpc(): void {
  function requireMainWindow(event: Electron.IpcMainInvokeEvent): void {
    const url = new URL(event.senderFrame?.url ?? 'about:blank')
    if (event.sender !== mainWindow?.webContents || url.origin !== DSH_URL) {
      throw new Error('请在 SIMFLOW 主窗口中修改配置。')
    }
  }

  function modelInput(raw: unknown): unknown {
    if (!raw || typeof raw !== 'object') return raw
    const values = raw as Record<string, unknown>
    return { ...values, apiKey: values.apiKey === '' ? loadSettings().apiKey : values.apiKey }
  }

  ipcMain.handle('desktop:clear-cache', event => {
    requireMainWindow(event)
    return clearCacheAndReload()
  })

  ipcMain.handle('models:load', event => {
    requireMainWindow(event)
    const settings = loadSettings()
    return {
      llmBaseUrl: settings.llmBaseUrl, model: settings.model, models: settings.models,
      availableModels: settings.availableModels, customModels: settings.customModels,
      modelContexts: settings.modelContexts, apiKey: '', hasApiKey: Boolean(settings.apiKey),
      configured: modelEnvironment(settings).CAE_MODELS_CONFIGURED === '1',
    }
  })

  ipcMain.handle('models:save', async (event, raw: unknown) => {
    requireMainWindow(event)
    if (dshRestart || cacheClear) throw new Error('应用正在刷新或重启，请稍后重试。')
    if (workflowStore().hasRunning()) throw new Error('仿真正在执行，保存模型配置会重启后台。请等当前阶段结束后保存。')
    const settings = parseModelConfiguration(modelInput(raw))
    saveSettings({ ...loadSettings(), ...settings })
    await restartDsh()
  })

  ipcMain.handle('models:discover', (event, raw: unknown) => {
    requireMainWindow(event)
    return discoverModels(modelInput(raw))
  })

  ipcMain.handle('models:test', (event, raw: unknown) => {
    requireMainWindow(event)
    return testModels(modelInput(raw))
  })

  ipcMain.handle('simulation:load', event => {
    requireMainWindow(event)
    const settings = loadSettings()
    return Object.fromEntries(SIMULATION_FIELDS.map(field => [field, settings[field]]))
  })

  ipcMain.handle('simulation:save', async (event, raw: unknown) => {
    requireMainWindow(event)
    if (dshRestart || cacheClear) throw new Error('应用正在刷新或重启，请稍后重试。')
    if (workflowStore().hasRunning()) throw new Error('仿真正在执行，保存软件配置会重启后台。请等当前阶段结束后保存。')
    saveSimulationSettings(raw)
    await restartDsh()
  })

  ipcMain.handle('simulation:browse', async (event, kind: unknown, title: unknown) => {
    requireMainWindow(event)
    if ((kind !== 'directory' && kind !== 'file') || typeof title !== 'string') {
      throw new Error('路径选择参数无效。')
    }
    const result = await dialog.showOpenDialog(mainWindow!, {
      title: `选择${title.slice(0, 100)}`,
      properties: kind === 'directory' ? ['openDirectory', 'createDirectory'] : ['openFile'],
    })
    return result.canceled ? null : result.filePaths[0]
  })

  ipcMain.handle('simulation:check-paths', (event, raw: unknown) => {
    requireMainWindow(event)
    const paths = parseSimulationSettings(raw, { validateService: false })
    return Object.fromEntries(SIMULATION_PATH_FIELDS.filter(field => field !== 'lsdyna' || (paths.solverLocation === 'local' && paths.localSolverType === 'software')).map(field => {
      const path = paths[field]
      if (!path) return [field, { valid: false, empty: true, message: '未配置，可稍后填写。' }]
      try {
        const stat = statSync(path)
        const valid = field === 'hyperworksHome' || field === 'workdir' ? stat.isDirectory() : stat.isFile()
        return [field, { valid, message: valid ? '路径可用。' : '路径类型不匹配，请重新选择。' }]
      } catch {
        return [field, { valid: false, message: '路径不存在或无法访问。' }]
      }
    }))
  })

  ipcMain.handle('simulation:check-service', (event, raw: unknown) => {
    requireMainWindow(event)
    return checkSolverService(raw)
  })

  ipcMain.handle('workflow:load', (event, sessionId: string) => {
    requireMainWindow(event)
    const state = workflowStore().load(sessionId)
    const settings = loadSettings()
    return { state, stages: STAGES, configuration: state ? missingSoftware(STAGES[state.current], settings) : null, workdir: settings.workdir }
  })
  ipcMain.handle('workflow:create', (event, sessionId: string) => {
    requireMainWindow(event)
    return workflowStore().create(sessionId)
  })
  ipcMain.handle('workflow:submit', (event, sessionId: string, revision: number, values: unknown) => {
    requireMainWindow(event)
    return workflowStore().submit(sessionId, revision, values, loadSettings())
  })
  ipcMain.handle('workflow:confirm', (event, sessionId: string, revision: number) => {
    requireMainWindow(event)
    return workflowStore().confirm(sessionId, revision)
  })
  ipcMain.handle('workflow:adjust', (event, sessionId: string, revision: number, feedback: unknown) => {
    requireMainWindow(event)
    return workflowStore().adjust(sessionId, revision, feedback)
  })
  ipcMain.handle('workflow:browse', async (event, sessionId: string, fieldId: string) => {
    requireMainWindow(event)
    const field = workflowField(workflowStore(), sessionId, fieldId, STAGES)
    const result = await dialog.showOpenDialog(mainWindow!, {
      title: `选择${field.label}`,
      properties: field.type === 'directory' ? ['openDirectory', 'createDirectory'] : ['openFile'],
      ...(field.extensions ? { filters: [{ name: field.label, extensions: field.extensions }] } : {}),
    })
    return result.canceled ? null : result.filePaths[0]
  })
  ipcMain.handle('workflow:open', async (event, sessionId: string, file: unknown) => {
    requireMainWindow(event)
    const error = await shell.openPath(workflowArtifact(workflowStore(), sessionId, file))
    if (error) throw new Error(error)
  })
  ipcMain.handle('workflow:preview', (event, sessionId: string, file: unknown) => {
    requireMainWindow(event)
    return workflowPreview(workflowStore(), sessionId, file)
  })
}

// ── Main window ────────────────────────────────────────────────────────────
function createMainWindow(): BrowserWindow {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 900,
    minHeight: 600,
    title: APP_NAME,
    icon: join(__dirname, '..', 'resources', 'icon.png'),
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      preload: join(__dirname, 'ui-preload.js'),
    },
    backgroundColor: '#06172f',
    show: false,
  })
  mainWindow.loadFile(join(__dirname, '..', 'resources', 'starting.html')).catch(error => {
    runtimeLog.write('main', `Cannot load startup page: ${error.message}`)
  })
  mainWindow.webContents.on('page-title-updated', event => {
    event.preventDefault()
    mainWindow?.setTitle(APP_NAME)
  })
  mainWindow.once('ready-to-show', () => { mainWindow?.show() })
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('http')) shell.openExternal(url)
    return { action: 'deny' }
  })
  enableEditingContextMenu(mainWindow)
  mainWindow.on('closed', () => { mainWindow = null })

  const menu = Menu.buildFromTemplate([
    {
      label: APP_NAME,
      submenu: [
        {
          label: '设置...',
          accelerator: 'CmdOrCtrl+,',
          click: () => mainWindow?.webContents.send('models:open-settings'),
        },
        { type: 'separator' },
        { role: 'quit', label: '退出' },
      ],
    },
    EDIT_MENU,
    {
      label: '视图',
      submenu: [
        { role: 'reload',       label: '刷新' },
        { role: 'forceReload',  label: '强制刷新' },
        {
          label: '清除缓存并刷新…',
          click: () => {
            void clearCacheAndReload().catch(error => {
              dialog.showErrorBox('清除缓存失败', error instanceof Error ? error.message : '请重启应用后重试。')
            })
          },
        },
        { type: 'separator' },
        { role: 'toggleDevTools', label: '开发者工具' },
        { type: 'separator' },
        { role: 'resetZoom',    label: '实际大小' },
        { role: 'zoomIn',       label: '放大' },
        { role: 'zoomOut',      label: '缩小' },
        { type: 'separator' },
        { role: 'togglefullscreen', label: '全屏' },
      ],
    },
  ])
  Menu.setApplicationMenu(menu)
  return mainWindow
}

// ── App lifecycle ──────────────────────────────────────────────────────────
const ownsInstance = app.requestSingleInstanceLock()
if (!ownsInstance) app.quit()

app.on('second-instance', () => {
  const win = mainWindow
  if (!win || win.isDestroyed()) return
  if (win.isMinimized()) win.restore()
  win.show()
  win.focus()
})

app.whenReady().then(async () => {
  if (!ownsInstance || quitting) return
  runtimeLog = new RuntimeLog(join(app.getPath('userData'), 'logs', 'startup.log'))
  runtimeLog.write('main', `${APP_NAME} ${app.getVersion()}; platform=${process.platform}; packaged=${IS_PACKAGED}`)
  registerIpc()

  try {
    launchingDsh = true
    const win = createMainWindow()
    try {
      await clearDesktopCache(win.webContents.session, DSH_URL)
    } catch (error) {
      runtimeLog.write('main', `Cannot clear desktop UI cache at startup: ${error instanceof Error ? error.message : String(error)}`)
    }
    await startDsh()
    if (quitting) return
    if (!win.isDestroyed()) await win.loadURL(dshUrl!)
    startupComplete = true
  } catch (err) {
    if (quitting) return
    runtimeLog.write('main', err instanceof Error ? err.message : String(err))
    dialog.showErrorBox(`${APP_NAME} — 启动失败`, runtimeLog.failure(err))
    app.quit()
  } finally {
    launchingDsh = false
  }
})

app.on('window-all-closed', () => {
  if ((startupComplete || launchingDsh) && process.platform !== 'darwin') app.quit()
})

app.on('before-quit', () => {
  quitting = true
  stopPythonMcpPreparations()
  if (dshProcess && !dshProcess.killed) {
    dshProcess.kill('SIGTERM')
  }
})

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0 && dshUrl) {
    createMainWindow().loadURL(dshUrl)
  }
})

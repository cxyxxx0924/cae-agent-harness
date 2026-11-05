import { app, BrowserWindow, shell, Menu, Tray, nativeImage, dialog } from 'electron'
import { ipcMain } from 'electron'
import { spawn, type ChildProcess } from 'node:child_process'
import { resolve, join, delimiter } from 'node:path'
import { existsSync, statSync } from 'node:fs'
import { createInterface } from 'node:readline'
import http from 'node:http'
import { loadSettings, saveSettings, isFirstRun, type CaeSettings } from './store'
import { parseModelSettings } from './model-settings'
import { SIMULATION_FIELDS, SIMULATION_PATH_FIELDS, parseSimulationSettings, simulationEnvironment, checkSolverService } from './simulation-settings'

// ── Constants ─────────────────────────────────────────────────────────────
const DSH_PORT          = Number(process.env.DSH_PORT ?? 3080)
const DSH_URL           = `http://127.0.0.1:${DSH_PORT}`
const STARTUP_TIMEOUT_MS = 60_000
const IS_PACKAGED       = app.isPackaged

// ── Paths ──────────────────────────────────────────────────────────────────
function resourcePath(...parts: string[]): string {
  return IS_PACKAGED
    ? join(process.resourcesPath, 'runtime', ...parts)
    : resolve(__dirname, '../../..', ...parts)
}

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

function preloadPath(): string {
  return join(__dirname, 'preload.js')
}

// ── State ──────────────────────────────────────────────────────────────────
let dshProcess:    ChildProcess | null  = null
let dshUrl: string | null = null
let startupComplete = false
let dshRestart: Promise<void> | null = null
let mainWindow:    BrowserWindow | null = null
let settingsWindow: BrowserWindow | null = null

// ── dsh lifecycle ─────────────────────────────────────────────────────────
function waitForDsh(proc: ChildProcess, timeoutMs: number): Promise<string> {
  return new Promise((resolve, reject) => {
    const output = createInterface({ input: proc.stdout! })
    let request: http.ClientRequest | undefined
    let settled = false
    const timeout = setTimeout(() => {
      finish(new Error(`dsh did not start within ${timeoutMs}ms`))
    }, timeoutMs)

    function finish(error?: Error, url?: string): void {
      if (settled) return
      settled = true
      clearTimeout(timeout)
      output.close()
      proc.off('error', onError)
      proc.off('exit', onExit)
      request?.destroy()
      if (error) reject(error)
      else resolve(url!)
    }

    function onError(error: Error): void {
      finish(error)
    }

    function onExit(code: number | null, signal: NodeJS.Signals | null): void {
      finish(new Error(`dsh exited before startup completed (${signal ?? code}). Check the dsh logs for details.`))
    }

    output.on('line', (line: string) => {
      const match = /^dsh web: (http:\/\/\S+)$/.exec(line)
      if (!match || request) return
      const url = new URL(match[1])
      if (url.origin !== DSH_URL || url.pathname !== '/' || !url.searchParams.get('token')) return
      request = http.get(url, response => {
        const authenticated = response.statusCode === 303 && Boolean(response.headers['set-cookie']?.length)
        response.resume()
        if (authenticated) finish(undefined, url.href)
        else finish(new Error(`dsh authentication failed (HTTP ${response.statusCode}).`))
      })
      request.setTimeout(5000, () => request?.destroy(new Error('dsh authentication request timed out.')))
      request.on('error', onError)
    })
    proc.once('error', onError)
    proc.once('exit', onExit)
  })
}

function spawnDsh(settings: CaeSettings): ChildProcess {
  const modelSettings = parseModelSettings(settings)
  const simulationEnv = simulationEnvironment(parseSimulationSettings(settings))
  const bin     = dshBin()
  const profile = profilePath()
  const env: NodeJS.ProcessEnv = {
    ...process.env,
    ELECTRON_RUN_AS_NODE: '1',
    DSH_PORT:           String(DSH_PORT),
    DSH_NO_OPEN_BROWSER: '1',
    // Saved desktop settings take precedence over the launch environment.
    DEEPSEEK_API_KEY:   modelSettings.apiKey,
    LLM_BASE_URL:       modelSettings.llmBaseUrl || process.env.LLM_BASE_URL || '',
    LLM_MODEL:          modelSettings.model,
    ...simulationEnv,
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
  }
  // Remove empty-string entries to avoid overriding child-process defaults
  for (const key of Object.keys(env)) {
    if (env[key] === '' && !(key in simulationEnv)) delete env[key]
  }
  const proc = spawn(nodeExecutable, [bin, 'web', '--patch', profile, '--no-open', '--host', '127.0.0.1', '--port', String(DSH_PORT)], {
    env,
    cwd: projectRoot(),
    stdio: ['ignore', 'pipe', 'pipe'],
    detached: false,
    shell: false,
    windowsHide: true,
  })
  proc.stdout?.on('data', (d: Buffer) => process.stdout.write(`[dsh] ${d}`))
  proc.stderr?.on('data', (d: Buffer) => process.stderr.write(`[dsh] ${d}`))
  proc.on('error', (error) => {
    process.stderr.write(`[dsh] ${error.message}\n`)
  })
  proc.on('exit', (code) => {
    process.stderr.write(`[dsh] exited with code ${code}\n`)
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
  dshProcess = spawnDsh(loadSettings())
  try {
    dshUrl = await waitForDsh(dshProcess, STARTUP_TIMEOUT_MS)
  } catch (error) {
    await stopDsh()
    throw error
  }
}

async function restartDsh(): Promise<void> {
  if (dshRestart) return dshRestart
  dshRestart = (async () => {
    await stopDsh()
    await startDsh()
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

// ── Settings window ────────────────────────────────────────────────────────
function openSettingsWindow(): BrowserWindow {
  if (settingsWindow && !settingsWindow.isDestroyed()) {
    settingsWindow.focus()
    return settingsWindow
  }
  settingsWindow = new BrowserWindow({
    width: 700,
    height: 620,
    minWidth: 580,
    minHeight: 500,
    title: 'CAE Agent — 设置',
    resizable: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: false,           // sandbox: false required for preload fs access
      preload: preloadPath(),
    },
    backgroundColor: '#0f172a',
    show: false,
    parent: mainWindow ?? undefined,
    modal: false,
  })
  settingsWindow.loadFile(
    join(__dirname, '..', 'resources', 'settings.html')
  )
  settingsWindow.once('ready-to-show', () => { settingsWindow?.show() })
  settingsWindow.on('closed', () => { settingsWindow = null })
  return settingsWindow
}

// ── IPC handlers ───────────────────────────────────────────────────────────
function registerIpc(): void {
  function requireMainWindow(event: Electron.IpcMainInvokeEvent): void {
    const url = new URL(event.senderFrame?.url ?? 'about:blank')
    if (event.sender !== mainWindow?.webContents || url.origin !== DSH_URL) {
      throw new Error('请在 CAE Agent 主窗口中配置仿真软件。')
    }
  }

  ipcMain.handle('simulation:load', event => {
    requireMainWindow(event)
    const settings = loadSettings()
    return Object.fromEntries(SIMULATION_FIELDS.map(field => [field, settings[field]]))
  })

  ipcMain.handle('simulation:save', async (event, raw: unknown) => {
    requireMainWindow(event)
    if (dshRestart) throw new Error('后台服务正在重启，请稍后重试。')
    const settings = parseSimulationSettings(raw)
    saveSettings({ ...loadSettings(), ...settings })
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

  ipcMain.handle('settings:load', () => loadSettings())
  ipcMain.handle('settings:check-service', (_event, raw: unknown) => checkSolverService(raw))

  ipcMain.handle('settings:save', async (_evt, raw: unknown) => {
    saveSettings(raw)
    // Close settings window, then restart dsh + reload main window
    settingsWindow?.webContents.send('settings:saved')
    settingsWindow?.close()
    if (!startupComplete) return
    try {
      await restartDsh()
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      dialog.showErrorBox('CAE Agent — 重启失败', msg)
    }
  })

  ipcMain.handle('settings:browse-exe', async (_evt, title: string) => {
    const win = settingsWindow ?? mainWindow
    const result = await dialog.showOpenDialog(win!, {
      title: `选择可执行文件 — ${title}`,
      properties: ['openFile'],
      filters: [
        { name: '可执行文件', extensions: ['exe'] },
        { name: '所有文件',   extensions: ['*']   },
      ],
    })
    return result.canceled ? null : result.filePaths[0]
  })

  ipcMain.handle('settings:browse-dir', async (_evt, title: string) => {
    const win = settingsWindow ?? mainWindow
    const result = await dialog.showOpenDialog(win!, {
      title: `选择目录 — ${title}`,
      properties: ['openDirectory', 'createDirectory'],
    })
    return result.canceled ? null : result.filePaths[0]
  })

  ipcMain.handle('settings:check-paths',
    async (_evt, paths: Record<string, string>) => {
      const result: Record<string, boolean> = {}
      for (const [key, p] of Object.entries(paths)) {
        result[key] = Boolean(p) && existsSync(p)
      }
      return result
    }
  )
}

// ── Main window ────────────────────────────────────────────────────────────
function createMainWindow(): void {
  if (!dshUrl) return
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 900,
    minHeight: 600,
    title: 'CAE Agent',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      preload: join(__dirname, 'ui-preload.js'),
    },
    backgroundColor: '#0f172a',
    show: false,
  })
  mainWindow.loadURL(dshUrl)
  mainWindow.webContents.on('page-title-updated', event => {
    event.preventDefault()
    mainWindow?.setTitle('CAE Agent')
  })
  mainWindow.once('ready-to-show', () => { mainWindow?.show() })
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('http')) shell.openExternal(url)
    return { action: 'deny' }
  })
  mainWindow.on('closed', () => { mainWindow = null })

  const menu = Menu.buildFromTemplate([
    {
      label: 'CAE Agent',
      submenu: [
        {
          label: '设置...',
          accelerator: 'CmdOrCtrl+,',
          click: () => openSettingsWindow(),
        },
        { type: 'separator' },
        { role: 'quit', label: '退出' },
      ],
    },
    {
      label: '视图',
      submenu: [
        { role: 'reload',       label: '刷新' },
        { role: 'forceReload',  label: '强制刷新' },
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
}

// ── App lifecycle ──────────────────────────────────────────────────────────
app.whenReady().then(async () => {
  registerIpc()

  const firstRun = isFirstRun()

  if (firstRun) {
    // Show settings window before dsh starts; wait for user to save
    await new Promise<void>(resolve => {
      const win = openSettingsWindow()
      // Resolve when the user clicks Save (main process closes the window)
      win.on('closed', () => resolve())
    })
  }

  while (true) {
    try {
      parseModelSettings(loadSettings())
      break
    } catch (error) {
      const { response } = await dialog.showMessageBox({
        type: 'warning',
        title: 'CAE Agent — 模型配置无效',
        message: error instanceof Error ? error.message : '请检查模型配置后重试。',
        buttons: ['打开设置', '退出'],
        cancelId: 1,
      })
      if (response === 1) { app.quit(); return }
      await new Promise<void>(resolve => {
        const win = openSettingsWindow()
        win.on('closed', () => resolve())
      })
    }
  }

  try {
    await startDsh()
    createMainWindow()
    startupComplete = true
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    dialog.showErrorBox('CAE Agent — 启动失败', msg)
    app.quit()
  }
})

app.on('window-all-closed', () => {
  if (startupComplete && process.platform !== 'darwin') app.quit()
})

app.on('before-quit', () => {
  if (dshProcess && !dshProcess.killed) {
    dshProcess.kill('SIGTERM')
  }
})

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createMainWindow()
})

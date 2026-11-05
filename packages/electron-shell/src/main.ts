import { app, BrowserWindow, shell, Menu, Tray, nativeImage, dialog } from 'electron'
import { ipcMain } from 'electron'
import { spawn, type ChildProcess } from 'node:child_process'
import { resolve, join } from 'node:path'
import { existsSync } from 'node:fs'
import http from 'node:http'
import { loadSettings, saveSettings, isFirstRun, type CaeSettings } from './store'

// ── Constants ─────────────────────────────────────────────────────────────
const DSH_PORT          = Number(process.env.DSH_PORT ?? 3080)
const DSH_URL           = `http://127.0.0.1:${DSH_PORT}`
const STARTUP_TIMEOUT_MS = 60_000
const IS_PACKAGED       = app.isPackaged

// ── Paths ──────────────────────────────────────────────────────────────────
function resourcePath(...parts: string[]): string {
  return IS_PACKAGED
    ? join(process.resourcesPath, ...parts)
    : resolve(__dirname, '../../..', ...parts)
}

function dshBin(): string {
  const candidates = [
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
let mainWindow:    BrowserWindow | null = null
let settingsWindow: BrowserWindow | null = null

// ── dsh lifecycle ─────────────────────────────────────────────────────────
function waitForDsh(timeoutMs: number): Promise<void> {
  const start = Date.now()
  return new Promise((res, rej) => {
    function probe() {
      http.get(`${DSH_URL}/api/health`, (r) => {
        if (r.statusCode !== undefined && r.statusCode < 500) res()
        else retry()
        r.resume()
      }).on('error', retry)
    }
    function retry() {
      if (Date.now() - start > timeoutMs) {
        rej(new Error(`dsh did not start within ${timeoutMs}ms`))
        return
      }
      setTimeout(probe, 800)
    }
    probe()
  })
}

function spawnDsh(settings: CaeSettings): ChildProcess {
  const bin     = dshBin()
  const profile = profilePath()
  const env: NodeJS.ProcessEnv = {
    ...process.env,
    ELECTRON_RUN_AS_NODE: '1',
    DSH_PORT:           String(DSH_PORT),
    DSH_NO_OPEN_BROWSER: '1',
    // Inject settings from store, allowing env overrides to take precedence
    DEEPSEEK_API_KEY:   settings.apiKey   || process.env.DEEPSEEK_API_KEY   || '',
    LLM_BASE_URL:       settings.llmBaseUrl || process.env.LLM_BASE_URL     || '',
    LLM_MODEL:          settings.model    || process.env.LLM_MODEL          || '',
    CAE_HMBATCH:        settings.hmbatch  || process.env.CAE_HMBATCH        || '',
    CAE_HYPERVIEW:      settings.hyperview || process.env.CAE_HYPERVIEW     || '',
    CAE_LSDYNA:         settings.lsdyna   || process.env.CAE_LSDYNA         || '',
    CAE_WORKDIR:        settings.workdir  || process.env.CAE_WORKDIR        || '',
    HYPERWORKS_HOME:    settings.hyperworksHome || process.env.HYPERWORKS_HOME || '',
  }
  // Remove empty-string entries to avoid overriding child-process defaults
  for (const key of Object.keys(env) as (keyof NodeJS.ProcessEnv)[]) {
    if (env[key] === '') delete env[key]
  }
  const proc = spawn('node', [bin, 'web', '--patch', profile, '--no-open'], {
    env,
    cwd: projectRoot(),
    stdio: ['ignore', 'pipe', 'pipe'],
    detached: false,
    shell: false,
  })
  proc.stdout?.on('data', (d: Buffer) => process.stdout.write(`[dsh] ${d}`))
  proc.stderr?.on('data', (d: Buffer) => process.stderr.write(`[dsh] ${d}`))
  proc.on('exit', (code) => {
    process.stderr.write(`[dsh] exited with code ${code}\n`)
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow
        .loadFile(join(__dirname, '..', 'resources', 'error.html'))
        .catch(() => { /* ignore */ })
    }
  })
  return proc
}

async function restartDsh(): Promise<void> {
  if (dshProcess && !dshProcess.killed) {
    dshProcess.kill('SIGTERM')
    await new Promise<void>(res => {
      dshProcess!.on('exit', () => res())
      setTimeout(() => res(), 3000)  // force-continue after 3s
    })
    dshProcess = null
  }
  const settings = loadSettings()
  dshProcess = spawnDsh(settings)
  await waitForDsh(STARTUP_TIMEOUT_MS)
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.loadURL(DSH_URL).catch(() => { /* ignore */ })
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
  ipcMain.handle('settings:load', () => loadSettings())

  ipcMain.handle('settings:save', async (_evt, raw: unknown) => {
    saveSettings(raw as CaeSettings)
    // Close settings window, then restart dsh + reload main window
    settingsWindow?.webContents.send('settings:saved')
    settingsWindow?.close()
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
    },
    backgroundColor: '#0f172a',
    show: false,
  })
  mainWindow.loadURL(DSH_URL)
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

  const settings = loadSettings()

  // Guard: require API key before starting dsh
  if (!settings.apiKey) {
    const { response } = await dialog.showMessageBox({
      type: 'warning',
      title: 'CAE Agent — 缺少 API Key',
      message: '尚未配置 API Key，无法启动 AI Agent。\n请在设置中填写后重试。',
      buttons: ['打开设置', '退出'],
    })
    if (response === 1) { app.quit(); return }
    await new Promise<void>(resolve => {
      const win = openSettingsWindow()
      win.on('closed', () => resolve())
    })
  }

  try {
    dshProcess = spawnDsh(loadSettings())
    await waitForDsh(STARTUP_TIMEOUT_MS)
    createMainWindow()
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    dialog.showErrorBox('CAE Agent — 启动失败', msg)
    app.quit()
  }
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

app.on('before-quit', () => {
  if (dshProcess && !dshProcess.killed) {
    dshProcess.kill('SIGTERM')
  }
})

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createMainWindow()
})

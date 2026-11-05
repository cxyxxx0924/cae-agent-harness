import { app, BrowserWindow, shell, Menu, Tray, nativeImage, dialog } from 'electron'
import { spawn, type ChildProcess } from 'node:child_process'
import { resolve, join } from 'node:path'
import { existsSync } from 'node:fs'
import http from 'node:http'

const DSH_PORT = Number(process.env.DSH_PORT ?? 3080)
const DSH_URL = `http://127.0.0.1:${DSH_PORT}`
const STARTUP_TIMEOUT_MS = 60_000
const IS_PACKAGED = app.isPackaged

function resourcePath(...parts: string[]): string {
  return IS_PACKAGED
    ? join(process.resourcesPath, ...parts)
    : resolve(__dirname, '../../..', ...parts)
}

function dshBin(): string {
  const candidates = [
    join(__dirname, '../../node_modules/@deepseek-ai/dsh/bin/dsh.js'),
    join(__dirname, '../../../node_modules/@deepseek-ai/dsh/bin/dsh.js'),
    resolve(__dirname, '../../../../node_modules/.bin/dsh'),
  ]
  for (const c of candidates) {
    if (existsSync(c)) return c
  }
  throw new Error('Cannot locate @deepseek-ai/dsh binary. Run pnpm install first.')
}

function profilePath(): string {
  return resourcePath('config', 'cae-airbag.cordis.yml')
}

let dshProcess: ChildProcess | null = null
let mainWindow: BrowserWindow | null = null
let tray: Tray | null = null

function waitForDsh(timeoutMs: number): Promise<void> {
  const start = Date.now()
  return new Promise((resolve, reject) => {
    function probe() {
      http.get(`${DSH_URL}/api/health`, (res) => {
        if (res.statusCode !== undefined && res.statusCode < 500) {
          resolve()
        } else {
          retry()
        }
        res.resume()
      }).on('error', retry)
    }
    function retry() {
      if (Date.now() - start > timeoutMs) {
        reject(new Error(`dsh did not start within ${timeoutMs}ms`))
        return
      }
      setTimeout(probe, 800)
    }
    probe()
  })
}

function spawnDsh(): ChildProcess {
  const bin = dshBin()
  const profile = profilePath()
  const env: NodeJS.ProcessEnv = {
    ...process.env,
    DSH_PORT: String(DSH_PORT),
    DSH_NO_OPEN_BROWSER: '1',
  }
  const proc = spawn(process.execPath, [bin, '--profile', profile], {
    env,
    stdio: ['ignore', 'pipe', 'pipe'],
    detached: false,
  })
  proc.stdout?.on('data', (d: Buffer) => process.stdout.write(`[dsh] ${d}`))
  proc.stderr?.on('data', (d: Buffer) => process.stderr.write(`[dsh] ${d}`))
  proc.on('exit', (code) => {
    process.stderr.write(`[dsh] exited with code ${code}\n`)
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.loadFile(join(__dirname, '..', 'resources', 'error.html'))
        .catch(() => { /* ignore */ })
    }
  })
  return proc
}

function createWindow(): void {
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
        { role: 'quit' },
      ],
    },
    {
      label: '视图',
      submenu: [
        { role: 'reload' },
        { role: 'forceReload' },
        { type: 'separator' },
        { role: 'toggleDevTools' },
        { type: 'separator' },
        { role: 'resetZoom' },
        { role: 'zoomIn' },
        { role: 'zoomOut' },
        { type: 'separator' },
        { role: 'togglefullscreen' },
      ],
    },
  ])
  Menu.setApplicationMenu(menu)
}

app.whenReady().then(async () => {
  try {
    dshProcess = spawnDsh()
    await waitForDsh(STARTUP_TIMEOUT_MS)
    createWindow()
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
  if (BrowserWindow.getAllWindows().length === 0) createWindow()
})

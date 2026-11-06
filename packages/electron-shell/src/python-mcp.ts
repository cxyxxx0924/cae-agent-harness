import { spawn, type ChildProcess } from 'node:child_process'
import { existsSync, statSync } from 'node:fs'
import { join } from 'node:path'
import type { SimulationSettings } from './simulation-settings'

/**
 * The packaged Windows application must not depend on pypi.org being reachable.
 * Keep this overridable through UV_INDEX_URL/CAE_UV_INDEX_URL for other networks.
 */
export const DEFAULT_WINDOWS_UV_INDEX_URL = 'https://pypi.tuna.tsinghua.edu.cn/simple'

export interface PythonMcpProject {
  id: 'hyperworks' | 'qilan-solve'
  directory: string
  entrypoint: string
}

interface PreparationState {
  process?: ChildProcess
  retry?: ReturnType<typeof setTimeout>
}

const preparations = new Map<string, PreparationState>()
const PREPARATION_RETRY_MS = 30_000

function isDirectory(path: string): boolean {
  if (!path) return false
  try {
    return statSync(path).isDirectory()
  } catch {
    return false
  }
}

function isFile(path: string): boolean {
  if (!path) return false
  try {
    return statSync(path).isFile()
  } catch {
    return false
  }
}

function virtualEnvironmentEntrypoint(directory: string, command: string): string {
  const bin = process.platform === 'win32' ? 'Scripts' : 'bin'
  const suffix = process.platform === 'win32' ? '.exe' : ''
  return join(directory, '.venv', bin, `${command}${suffix}`)
}

/**
 * Return the Python MCP projects that are usable with the saved simulation
 * settings. Invalid default paths do not start uv or cause dsh to wait.
 */
export function pythonMcpProjects(settings: SimulationSettings, root: string): PythonMcpProject[] {
  const projects: PythonMcpProject[] = []
  const hyperworksDirectory = join(root, 'packages', 'hyperworks-mcp')
  const qilanDirectory = join(root, 'packages', 'qilan-solve')

  if (isDirectory(settings.hyperworksHome)) {
    projects.push({
      id: 'hyperworks',
      directory: hyperworksDirectory,
      entrypoint: virtualEnvironmentEntrypoint(hyperworksDirectory, 'hyperworks-mcp'),
    })
  }

  const usesLocalSolverSoftware = settings.solverLocation === 'local' && settings.localSolverType === 'software'
  if (usesLocalSolverSoftware && isFile(settings.lsdyna)) {
    projects.push({
      id: 'qilan-solve',
      directory: qilanDirectory,
      entrypoint: virtualEnvironmentEntrypoint(qilanDirectory, 'qilan-solve-mcp'),
    })
  }

  return projects
}

/**
 * Flags consumed by cordis. A flag is explicit in the desktop process so a
 * missing configured path disables only that optional MCP. Direct `dsh` usage
 * without these flags keeps the profile's environment-variable behaviour.
 */
export function pythonMcpFeatureEnvironment(settings: SimulationSettings): Record<string, string> {
  return {
    CAE_ENABLE_HYPERWORKS_MCP: isDirectory(settings.hyperworksHome) ? '1' : '0',
    CAE_ENABLE_QILAN_MCP: settings.solverLocation === 'local'
      && settings.localSolverType === 'software'
      && isFile(settings.lsdyna) ? '1' : '0',
  }
}

export function uvEnvironment(base: NodeJS.ProcessEnv, packagedWindows: boolean): NodeJS.ProcessEnv {
  const env = { ...base }
  const configuredIndex = env.CAE_UV_INDEX_URL || env.UV_INDEX_URL || env.UV_DEFAULT_INDEX
  if (configuredIndex) {
    env.UV_INDEX_URL = configuredIndex
    env.UV_DEFAULT_INDEX = configuredIndex
  } else if (packagedWindows) {
    env.UV_INDEX_URL = DEFAULT_WINDOWS_UV_INDEX_URL
    env.UV_DEFAULT_INDEX = DEFAULT_WINDOWS_UV_INDEX_URL
  }
  return env
}

function logPreparation(id: PythonMcpProject['id'], stream: 'stdout' | 'stderr', chunk: Buffer): void {
  const text = chunk.toString()
  if (text) process[stream].write(`[uv:${id}] ${text}`)
}

function prepareProject(project: PythonMcpProject, uv: string, env: NodeJS.ProcessEnv): void {
  const existing = preparations.get(project.directory)
  if (existing?.process || existing?.retry) return

  if (existsSync(project.entrypoint)) {
    preparations.delete(project.directory)
    return
  }

  // uv.lock includes registry and artifact URLs. Allow uv to refresh those
  // URLs for a configured mirror while preferring the versions already locked.
  const child = spawn(uv, ['sync', '--project', project.directory], {
    cwd: project.directory,
    env,
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
    shell: false,
  })
  preparations.set(project.directory, { process: child })
  child.stdout?.on('data', chunk => logPreparation(project.id, 'stdout', chunk))
  child.stderr?.on('data', chunk => logPreparation(project.id, 'stderr', chunk))
  child.once('error', error => {
    process.stderr.write(`[uv:${project.id}] ${error.message}\n`)
  })
  // Failed spawns emit error and close, but do not emit exit.
  child.once('close', code => {
    const state = preparations.get(project.directory)
    if (!state || state.process !== child) return
    state.process = undefined
    if (code === 0 && existsSync(project.entrypoint)) {
      preparations.delete(project.directory)
      process.stdout.write(`[uv:${project.id}] environment ready\n`)
      return
    }
    process.stderr.write(`[uv:${project.id}] sync exited with code ${code ?? 'unknown'}; retrying in ${PREPARATION_RETRY_MS}ms\n`)
    state.retry = setTimeout(() => {
      state.retry = undefined
      prepareProject(project, uv, env)
    }, PREPARATION_RETRY_MS)
    state.retry.unref()
  })
}

/**
 * Start dependency preparation without putting it on dsh's startup critical
 * path. MCP clients launch the virtualenv entrypoints directly and reconnect
 * while this work is running, without waiting for uv's environment locks.
 */
export function preparePythonMcpEnvironments(
  settings: SimulationSettings,
  root: string,
  uv: string,
  env: NodeJS.ProcessEnv,
): void {
  const projects = pythonMcpProjects(settings, root)
  for (const project of projects) prepareProject(project, uv, env)
}

export function stopPythonMcpPreparations(): void {
  for (const state of preparations.values()) {
    if (state.retry) clearTimeout(state.retry)
    if (state.process && state.process.exitCode === null && state.process.signalCode === null) {
      state.process.kill('SIGTERM')
    }
  }
  preparations.clear()
}

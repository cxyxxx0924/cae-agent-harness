import { app } from 'electron'
import { readFileSync, writeFileSync, existsSync } from 'node:fs'
import { join } from 'node:path'

export interface CaeSettings {
  hmbatch: string
  hyperview: string
  lsdyna: string
  workdir: string
  hyperworksHome: string
  apiKey: string
  llmBaseUrl: string
  model: string
}

export const SIMULATION_FIELDS = ['hyperworksHome', 'hmbatch', 'hyperview', 'lsdyna', 'workdir'] as const
export type SimulationSettings = Pick<CaeSettings, typeof SIMULATION_FIELDS[number]>

export function parseSimulationSettings(raw: unknown): SimulationSettings {
  if (!raw || typeof raw !== 'object') throw new Error('仿真配置格式无效。')
  const settings = {} as SimulationSettings
  for (const field of SIMULATION_FIELDS) {
    const value = (raw as Record<string, unknown>)[field]
    if (typeof value !== 'string' || value.includes('\0') || value.length > 32768) {
      throw new Error('仿真路径格式无效，请重新填写。')
    }
    settings[field] = value.trim()
  }
  return settings
}

const DEFAULTS: CaeSettings = {
  hmbatch: 'C:\\Altair\\2023\\hwdesktop\\hw\\bin\\win64\\hmbatch.exe',
  hyperview: 'C:\\Altair\\2023\\hwdesktop\\hw\\bin\\win64\\hw.exe',
  lsdyna: 'C:\\LSTC\\ls971_s_R13.1_winx64_ifort131.exe',
  workdir: 'D:\\cae_projects\\airbag',
  hyperworksHome: 'C:\\Altair\\2023',
  apiKey: '',
  llmBaseUrl: '',
  model: 'deepseek-chat',
}

function storePath(): string {
  return join(app.getPath('userData'), 'cae-settings.json')
}

export function loadSettings(): CaeSettings {
  try {
    const p = storePath()
    if (existsSync(p)) {
      return { ...DEFAULTS, ...JSON.parse(readFileSync(p, 'utf8')) } as CaeSettings
    }
  } catch {
    // ignore corrupt file — fall through to defaults
  }
  return { ...DEFAULTS }
}

export function saveSettings(s: CaeSettings): void {
  writeFileSync(storePath(), JSON.stringify(s, null, 2), 'utf8')
}

export function isFirstRun(): boolean {
  return !existsSync(storePath())
}

import { app } from 'electron'
import { readFileSync, writeFileSync, existsSync } from 'node:fs'
import { join } from 'node:path'
import { DEFAULT_MODEL, parseModelConfiguration, type ModelConfiguration } from './model-settings'
import { DEFAULT_SOLVER_SETTINGS, parseSimulationSettings, type SimulationSettings } from './simulation-settings'

export interface CaeSettings extends SimulationSettings, ModelConfiguration {}

const DEFAULTS: CaeSettings = {
  ...DEFAULT_SOLVER_SETTINGS,
  hmbatch: 'C:\\Altair\\2023\\hwdesktop\\hw\\bin\\win64\\hmbatch.exe',
  hyperview: 'C:\\Altair\\2023\\hwdesktop\\hw\\bin\\win64\\hw.exe',
  lsdyna: 'C:\\LSTC\\ls971_s_R13.1_winx64_ifort131.exe',
  workdir: 'D:\\cae_projects\\airbag',
  hyperworksHome: 'C:\\Altair\\2023',
  apiKey: '',
  llmBaseUrl: '',
  model: DEFAULT_MODEL,
  models: [],
  availableModels: [],
}

function storePath(): string {
  return join(app.getPath('userData'), 'cae-settings.json')
}

export function loadSettings(): CaeSettings {
  try {
    const p = storePath()
    if (existsSync(p)) {
      const saved = JSON.parse(readFileSync(p, 'utf8'))
      const models = saved.models ?? [saved.model || DEFAULT_MODEL]
      return { ...DEFAULTS, ...saved, models, availableModels: saved.availableModels ?? models } as CaeSettings
    }
  } catch {
    // ignore corrupt file — fall through to defaults
  }
  return { ...DEFAULTS, models: [], availableModels: [] }
}

export function saveSettings(raw: unknown): void {
  const settings: CaeSettings = { ...parseModelConfiguration(raw), ...parseSimulationSettings(raw) }
  writeFileSync(storePath(), JSON.stringify(settings, null, 2), 'utf8')
}

export function isFirstRun(): boolean {
  return !existsSync(storePath())
}

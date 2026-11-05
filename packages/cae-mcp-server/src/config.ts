import { readFileSync, existsSync } from 'node:fs'
import { resolve } from 'node:path'
import yaml from 'js-yaml'

interface RawConfig {
  windows?: { hmbatch?: string; hyperview?: string; lsdyna?: string }
  workdir?: string
}

function loadYaml(): RawConfig {
  const paths = [
    resolve(__dirname, '../../..', 'config', 'config.local.yaml'),
    resolve(__dirname, '../../..', 'config', 'config.yaml'),
  ]
  for (const p of paths) {
    if (existsSync(p)) return yaml.load(readFileSync(p, 'utf8')) as RawConfig
  }
  return {}
}

const raw = loadYaml()

export const CAE_CONFIG = {
  hmbatch: process.env.CAE_HMBATCH ?? raw.windows?.hmbatch
    ?? 'C:\\Altair\\2023\\hwdesktop\\hw\\bin\\win64\\hmbatch.exe',
  hyperview: process.env.CAE_HYPERVIEW ?? raw.windows?.hyperview
    ?? 'C:\\Altair\\2023\\hwdesktop\\hw\\bin\\win64\\hw.exe',
  lsdyna: process.env.CAE_LSDYNA ?? raw.windows?.lsdyna
    ?? 'C:\\LSTC\\ls971_s_R13.1_winx64_ifort131.exe',
  workdir: process.env.CAE_WORKDIR ?? raw.workdir ?? 'D:\\cae_projects\\airbag',
  solver: {
    location: process.env.CAE_SOLVER_LOCATION || 'local',
    localType: process.env.CAE_LOCAL_SOLVER_TYPE || 'software',
    serviceUrl: process.env.CAE_SOLVER_SERVICE_URL ?? '',
    serviceToken: process.env.CAE_SOLVER_SERVICE_TOKEN ?? '',
  },
  tclDir: resolve(__dirname, 'tcl'),
} as const

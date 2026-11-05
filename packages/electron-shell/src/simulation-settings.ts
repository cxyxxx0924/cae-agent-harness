export const SIMULATION_PATH_FIELDS = ['hyperworksHome', 'hmbatch', 'hyperview', 'lsdyna', 'workdir'] as const

export const DEFAULT_SOLVER_SETTINGS = {
  solverLocation: 'local',
  localSolverType: 'software',
  solverServerUrl: '',
  solverServerToken: '',
  solverLocalServiceUrl: 'http://127.0.0.1:8000',
  solverLocalServiceToken: '',
} as const

export const SIMULATION_FIELDS = [...SIMULATION_PATH_FIELDS, ...Object.keys(DEFAULT_SOLVER_SETTINGS) as (keyof typeof DEFAULT_SOLVER_SETTINGS)[]] as const

export interface SimulationSettings {
  hyperworksHome: string
  hmbatch: string
  hyperview: string
  lsdyna: string
  workdir: string
  solverLocation: 'local' | 'server'
  localSolverType: 'software' | 'service'
  solverServerUrl: string
  solverServerToken: string
  solverLocalServiceUrl: string
  solverLocalServiceToken: string
}

export function solverServiceSettings(settings: SimulationSettings): { url: string; token: string } | null {
  if (settings.solverLocation === 'server') {
    return { url: settings.solverServerUrl, token: settings.solverServerToken }
  }
  if (settings.localSolverType === 'service') {
    return { url: settings.solverLocalServiceUrl, token: settings.solverLocalServiceToken }
  }
  return null
}

export function parseSimulationSettings(raw: unknown, options: { validateService?: boolean } = {}): SimulationSettings {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw new Error('仿真配置格式无效。')
  const values = { ...DEFAULT_SOLVER_SETTINGS, ...raw }
  const settings = {} as SimulationSettings
  for (const field of SIMULATION_FIELDS) {
    const value = (values as Record<string, unknown>)[field]
    if (typeof value !== 'string' || value.includes('\0') || value.length > 32768) {
      throw new Error('仿真配置格式无效，请重新填写。')
    }
    ;(settings as unknown as Record<string, string>)[field] = value.trim()
  }
  if (!['local', 'server'].includes(settings.solverLocation)) throw new Error('请选择本地或服务端求解。')
  if (!['software', 'service'].includes(settings.localSolverType)) throw new Error('请选择本地软件或本地求解服务。')

  const service = solverServiceSettings(settings)
  if (service && options.validateService !== false) {
    let endpoint: URL
    try {
      if (!/^https?:\/\//i.test(service.url) || /\s/.test(service.url)) throw new Error('Invalid URL')
      endpoint = new URL(service.url)
    } catch {
      throw new Error('求解服务地址必须是完整的 http:// 或 https:// 网址。')
    }
    if (endpoint.username || endpoint.password || endpoint.search || endpoint.hash) {
      throw new Error('求解服务地址不能包含账号、密码、查询参数或片段；令牌请单独填写。')
    }
    if (service.token && /[^\x21-\x7e]/.test(service.token)) {
      throw new Error('求解服务令牌不能包含空白或非 ASCII 字符。')
    }
  }
  return settings
}

export function simulationEnvironment(settings: SimulationSettings): Record<string, string> {
  const service = solverServiceSettings(settings)
  return {
    CAE_HMBATCH: settings.hmbatch,
    CAE_HYPERVIEW: settings.hyperview,
    CAE_LSDYNA: service ? '' : settings.lsdyna,
    CAE_WORKDIR: settings.workdir,
    HYPERWORKS_HOME: settings.hyperworksHome,
    CAE_SOLVER_LOCATION: settings.solverLocation,
    CAE_LOCAL_SOLVER_TYPE: settings.localSolverType,
    CAE_SOLVER_SERVICE_URL: service?.url ?? '',
    CAE_SOLVER_SERVICE_TOKEN: service?.token ?? '',
  }
}

export async function checkSolverService(raw: unknown): Promise<{ valid: boolean; message: string }> {
  const settings = parseSimulationSettings(raw)
  const service = solverServiceSettings(settings)
  if (!service) throw new Error('当前使用本地软件，请通过“检查路径”检查求解器。')
  try {
    const response = await fetch(`${service.url.replace(/\/+$/, '')}/health`, {
      headers: service.token ? { Authorization: `Bearer ${service.token}` } : {},
      signal: AbortSignal.timeout(5000),
      redirect: 'error',
    })
    if (!response.ok) return { valid: false, message: `求解服务检查失败（HTTP ${response.status}），请检查地址和令牌。` }
    const health = await response.json() as { status?: unknown }
    if (health?.status !== 'ok') return { valid: false, message: '服务未就绪，或未提供兼容的健康检查接口。' }
    return { valid: true, message: '求解服务连接正常。' }
  } catch {
    return { valid: false, message: '无法连接求解服务，请检查服务是否启动、地址及网络连接。' }
  }
}

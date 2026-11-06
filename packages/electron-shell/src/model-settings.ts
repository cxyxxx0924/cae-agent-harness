export const DEFAULT_MODEL = 'deepseek-flash'

export interface ModelSettings {
  apiKey: string
  llmBaseUrl: string
  model: string
}

export interface ModelConfiguration extends ModelSettings {
  models: string[]
}

export function parseModelSettings(raw: unknown): ModelSettings {
  if (!raw || typeof raw !== 'object') throw new Error('模型配置格式无效。')
  const values = raw as Record<string, unknown>
  for (const field of ['apiKey', 'llmBaseUrl', 'model']) {
    if (typeof values[field] !== 'string' || values[field].includes('\0')) {
      throw new Error('模型配置格式无效，请重新填写。')
    }
  }

  const apiKey = (values.apiKey as string).trim()
  const llmBaseUrl = (values.llmBaseUrl as string).trim()
  const model = (values.model as string).trim() || DEFAULT_MODEL

  if (!apiKey) throw new Error('API Key 不能为空。')
  if (/^https?:\/\//i.test(apiKey)) {
    throw new Error('API Key 应填写密钥，不能填写网址。请检查是否与 API Base URL 填反。')
  }
  if (/\s/.test(apiKey)) throw new Error('API Key 不能包含空白字符。')

  if (llmBaseUrl) {
    let endpoint: URL
    try {
      if (!/^https?:\/\//i.test(llmBaseUrl) || /\s/.test(llmBaseUrl)) throw new Error('Invalid endpoint')
      endpoint = new URL(llmBaseUrl)
    } catch {
      throw new Error('API Base URL 必须是完整的 http:// 或 https:// 网址，例如 https://api.deepseek.com/v1。')
    }
    if (!['http:', 'https:'].includes(endpoint.protocol) || !endpoint.hostname) {
      throw new Error('API Base URL 必须是完整的 http:// 或 https:// 网址。')
    }
    if (endpoint.username || endpoint.password || endpoint.search || endpoint.hash) {
      throw new Error('API Base URL 不能包含账号、密码、查询参数或片段；密钥请填写在 API Key 中。')
    }
  }

  if (/\s/.test(model)) throw new Error('模型 ID 不能包含空白字符。')
  return { apiKey, llmBaseUrl, model }
}

export function parseModelConfiguration(raw: unknown): ModelConfiguration {
  const settings = parseModelSettings(raw)
  const models = (raw as Record<string, unknown>).models
  if (models !== undefined && (!Array.isArray(models) || models.length > 1000 || models.some(id =>
    typeof id !== 'string' || !id.trim() || /[\s\0]/.test(id.trim()),
  ))) {
    throw new Error('模型列表格式无效，请填写模型 ID，每行一个。')
  }
  const alternatives = (models as string[] | undefined) ?? []
  const normalized = [...new Set([settings.model, ...alternatives.map(id => id.trim())])]
  if (normalized.length > 1000) throw new Error('模型列表最多支持 1000 个模型，请删除多余的模型 ID。')
  return { ...settings, models: normalized }
}

export async function discoverModels(raw: unknown): Promise<string[]> {
  const { apiKey, llmBaseUrl } = parseModelSettings({ ...(raw as object), model: DEFAULT_MODEL })
  const url = `${(llmBaseUrl || 'https://api.deepseek.com/v1').replace(/\/+$/, '')}/models`
  let response: Response
  try {
    response = await fetch(url, {
      headers: { Authorization: `Bearer ${apiKey}` },
      signal: AbortSignal.timeout(10_000),
      redirect: 'error',
    })
  } catch {
    throw new Error('获取模型列表失败，请检查接口地址和网络，或手动填写模型 ID。')
  }
  if (!response.ok) throw new Error(`获取模型列表失败（HTTP ${response.status}），请检查 API Key 和接口地址，或手动填写模型 ID。`)
  let body: unknown
  try {
    body = await response.json()
  } catch {
    throw new Error('接口未返回有效的模型列表，请手动填写模型 ID。')
  }
  const entries = (body as { data?: unknown } | null)?.data
  const models = Array.isArray(entries) ? [...new Set(entries.flatMap(entry =>
    entry && typeof entry.id === 'string' && entry.id && !/[\s\0]/.test(entry.id) ? [entry.id] : [],
  ))].slice(0, 999) : []
  if (!models.length) throw new Error('接口未返回可用模型，请手动填写模型 ID。')
  return models
}

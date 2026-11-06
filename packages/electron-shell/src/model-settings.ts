export const DEFAULT_MODEL = 'deepseek-flash'
export const DEFAULT_MODEL_CONTEXT_WINDOW = 65_536
export const MAX_MODEL_CONTEXT_WINDOW = 10_000_000

const KNOWN_CONTEXT_WINDOWS: Record<string, number> = {
  'deepseek-flash': 1_000_000,
  'deepseek-v4-pro': 1_000_000,
}

export interface ModelSettings {
  apiKey: string
  llmBaseUrl: string
  model: string
}

export interface ModelConfiguration extends ModelSettings {
  models: string[]
  availableModels: string[]
  customModels: string[]
  modelContexts: Record<string, number>
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
  const values = raw as Record<string, unknown>
  const models = parseModelList(values.models === undefined ? [settings.model] : values.models)
  const availableModels = parseModelList(values.availableModels === undefined ? models : values.availableModels)
  const customModels = parseModelList(values.customModels === undefined ? [] : values.customModels)
  const modelContexts = parseModelContexts(values.modelContexts)
  if (!models.length) throw new Error('请至少选择一个模型。')
  if (!models.includes(settings.model)) throw new Error('请从已选模型中选择默认模型。')
  const available = new Set(availableModels)
  if (models.some(id => !available.has(id))) throw new Error('所选模型已不在当前接口的列表中，请重新获取并选择。')
  if (customModels.some(id => !available.has(id))) throw new Error('自定义模型必须保留在模型列表中。')
  for (const [id, contextWindow] of Object.entries(KNOWN_CONTEXT_WINDOWS)) {
    if (available.has(id) && modelContexts[id] === undefined) modelContexts[id] = contextWindow
  }
  return { ...settings, models, availableModels, customModels, modelContexts }
}

export function modelEnvironment(raw: unknown): Record<string, string> {
  try {
    const settings = parseModelConfiguration(raw)
    return {
      CAE_MODELS_CONFIGURED: '1',
      DEEPSEEK_API_KEY: settings.apiKey,
      LLM_BASE_URL: settings.llmBaseUrl || 'https://api.deepseek.com/v1',
      LLM_MODEL: settings.model,
      CAE_MODELS: JSON.stringify(settings.models),
      CAE_MODEL_CONTEXT_WINDOWS: JSON.stringify(settings.modelContexts),
    }
  } catch {
    return {
      CAE_MODELS_CONFIGURED: '0',
      DEEPSEEK_API_KEY: '',
      LLM_BASE_URL: '',
      LLM_MODEL: '',
      CAE_MODELS: '[]',
      CAE_MODEL_CONTEXT_WINDOWS: '{}',
    }
  }
}

function parseModelList(raw: unknown): string[] {
  if (!Array.isArray(raw) || raw.length > 1000 || raw.some(id =>
    typeof id !== 'string' || !id.trim() || /[\s\0]/.test(id.trim()),
  )) {
    throw new Error('模型列表格式无效，请重新获取模型列表。')
  }
  return [...new Set(raw.map(id => id.trim()))]
}

function parseModelContexts(raw: unknown): Record<string, number> {
  if (raw === undefined) return {}
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    throw new Error('模型上下文配置格式无效，请重新填写。')
  }
  const entries = Object.entries(raw)
  if (entries.length > 1000) throw new Error('模型上下文配置格式无效，请重新获取模型列表。')
  const contexts: Record<string, number> = {}
  for (const [id, contextWindow] of entries) {
    if (!id.trim() || /[\s\0]/.test(id) || !Number.isInteger(contextWindow) ||
      (contextWindow as number) < 1 || (contextWindow as number) > MAX_MODEL_CONTEXT_WINDOW) {
      throw new Error('上下文窗口必须是 1 到 10,000,000 之间的整数。')
    }
    contexts[id] = contextWindow as number
  }
  return contexts
}

function contextWindowFromEntry(entry: Record<string, unknown>): number | undefined {
  const fields = ['context_length', 'context_window', 'contextWindow', 'max_context_length', 'max_input_tokens']
  for (const field of fields) {
    const value = entry[field]
    const parsed = typeof value === 'number' ? value : typeof value === 'string' && /^\d+$/.test(value) ? Number(value) : NaN
    if (Number.isInteger(parsed) && parsed > 0 && parsed <= MAX_MODEL_CONTEXT_WINDOW) return parsed
  }
  return undefined
}

export interface DiscoveredModels {
  models: string[]
  modelContexts: Record<string, number>
}

export async function discoverModels(raw: unknown): Promise<DiscoveredModels> {
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
    throw new Error('获取模型列表失败，请检查接口地址和网络后重试。')
  }
  if (!response.ok) throw new Error(`获取模型列表失败（HTTP ${response.status}），请检查 API Key 和接口地址后重试。`)
  let body: unknown
  try {
    body = await response.json()
  } catch {
    throw new Error('接口未返回有效的模型列表，请检查接口地址后重试。')
  }
  const entries = (body as { data?: unknown } | null)?.data
  if (!Array.isArray(entries)) throw new Error('接口未返回有效的模型列表，请检查接口地址后重试。')
  const models: string[] = []
  const modelContexts: Record<string, number> = {}
  for (const entry of entries) {
    if (!entry || typeof entry !== 'object') continue
    const value = entry as Record<string, unknown>
    const id = value.id
    if (typeof id !== 'string' || !id || /[\s\0]/.test(id) || models.includes(id)) continue
    models.push(id)
    const contextWindow = contextWindowFromEntry(value)
    if (contextWindow) modelContexts[id] = contextWindow
  }
  const limitedModels = models.slice(0, 1000)
  for (const id of limitedModels) {
    if (modelContexts[id] === undefined && KNOWN_CONTEXT_WINDOWS[id] !== undefined) {
      modelContexts[id] = KNOWN_CONTEXT_WINDOWS[id]
    }
  }
  return {
    models: limitedModels,
    modelContexts: Object.fromEntries(Object.entries(modelContexts).filter(([id]) => limitedModels.includes(id))),
  }
}

export interface ModelCheck {
  id: string
  status: 'available' | 'unavailable' | 'unknown'
  message: string
}

export async function testModels(raw: unknown): Promise<ModelCheck[]> {
  const settings = parseModelConfiguration(raw)
  if (settings.models.length > 50) throw new Error('每次最多测试 50 个模型，请减少所选模型后重试。')
  const url = `${(settings.llmBaseUrl || 'https://api.deepseek.com/v1').replace(/\/+$/, '')}/chat/completions`
  const results: ModelCheck[] = []
  async function check(id: string): Promise<ModelCheck> {
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: { Authorization: `Bearer ${settings.apiKey}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: id, messages: [{ role: 'user', content: 'Hi' }], max_tokens: 1, stream: false }),
        signal: AbortSignal.timeout(15_000),
        redirect: 'error',
      })
      const body = await response.json().catch(() => null)
      if (response.ok && Array.isArray(body?.choices) && body.choices.length) {
        return { id, status: 'available', message: '测试通过' }
      }
      const code = typeof body?.error?.code === 'string' ? body.error.code : ''
      const message = typeof body?.error?.message === 'string' ? body.error.message : ''
      const unavailable = [400, 403, 404, 410, 422].includes(response.status) && (
        /^(model_not_found|invalid_model|unsupported_model|model_not_supported|model_not_available|model_access_denied)$/.test(code) ||
        /model.{0,100}(not.{0,20}(exist|found|available|supported)|does not exist|no.{0,20}(access|permission)|access denied|permission denied|disabled|retired)/i.test(message) ||
        /(no access|not have access|no permission|permission denied|access denied).{0,100}model/i.test(message) ||
        /模型.{0,60}(不存在|不可用|已下线|已停用|无权限|没有权限|不支持.{0,10}(对话|聊天))/.test(message)
      )
      if (unavailable) return { id, status: 'unavailable', message: '模型不存在、不支持对话或无访问权限' }
      return { id, status: 'unknown', message: `暂时无法确认（HTTP ${response.status}），已保留` }
    } catch {
      return { id, status: 'unknown', message: '连接失败或超时，已保留' }
    }
  }
  for (let index = 0; index < settings.models.length; index += 3) {
    results.push(...await Promise.all(settings.models.slice(index, index + 3).map(check)))
  }
  return results
}

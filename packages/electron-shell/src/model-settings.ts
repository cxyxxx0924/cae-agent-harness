export const DEFAULT_MODEL = 'deepseek-flash'

export interface ModelSettings {
  apiKey: string
  llmBaseUrl: string
  model: string
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

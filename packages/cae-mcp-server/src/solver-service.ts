import { z } from 'zod'
import type { SolveArgs } from './tools/lsdyna'

export interface SolverBackend {
  location: string
  localType: string
  serviceUrl: string
  serviceToken: string
}

const ServiceResultSchema = z.object({
  status: z.enum(['ok', 'warning', 'error']),
  exitCode: z.number().int().optional(),
  d3plot: z.string().nullable().optional(),
  logFile: z.string().nullable().optional(),
  log: z.string().optional(),
  message: z.string().optional(),
  terminationTime: z.number().optional(),
  lastSimTime: z.number().optional(),
  lastTimestep: z.string().optional(),
  lastCycle: z.number().int().optional(),
})

export function usesSolverService(config: SolverBackend): boolean {
  if (!['local', 'server'].includes(config.location) || !['software', 'service'].includes(config.localType)) {
    throw new Error('求解器配置无效，请在设置中重新选择求解位置和接入方式。')
  }
  return config.location === 'server' || config.localType === 'service'
}

export async function solveViaService(args: SolveArgs, config: SolverBackend): Promise<string> {
  let endpoint: URL
  try {
    if (!/^https?:\/\//i.test(config.serviceUrl) || /\s/.test(config.serviceUrl)) throw new Error('Invalid URL')
    endpoint = new URL(config.serviceUrl)
    if (endpoint.username || endpoint.password || endpoint.search || endpoint.hash) throw new Error('Invalid URL')
  } catch {
    throw new Error('求解服务地址无效，请在“设置 → 仿真软件”填写完整的 HTTP 或 HTTPS 地址。')
  }
  if (config.serviceToken && /[^\x21-\x7e]/.test(config.serviceToken)) throw new Error('求解服务令牌格式无效。')

  let response: Response
  try {
    response = await fetch(`${endpoint.href.replace(/\/+$/, '')}/solve`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(config.serviceToken ? { Authorization: `Bearer ${config.serviceToken}` } : {}),
      },
      body: JSON.stringify({ solver: 'lsdyna', ...args }),
      signal: AbortSignal.timeout(3_600_000),
      redirect: 'error',
    })
  } catch {
    throw new Error('求解服务请求超时或连接中断。请先在服务端确认任务状态，避免重复提交。')
  }
  if (!response.ok) throw new Error(`求解服务请求失败（HTTP ${response.status}），请检查服务地址、令牌和服务日志。`)

  let result: z.infer<typeof ServiceResultSchema>
  try {
    result = ServiceResultSchema.parse(await response.json())
  } catch {
    throw new Error('求解服务返回格式无效，需要返回兼容的求解结果 JSON。')
  }
  const redact = (text: string): string => config.serviceToken ? text.split(config.serviceToken).join('[redacted]') : text
  if (result.status === 'error') throw new Error(`求解服务执行失败：${redact(result.message || result.log || '请检查服务端日志。')}`)
  if (result.log) result.log = redact(result.log)
  if (result.message) result.message = redact(result.message)
  if (result.exitCode !== undefined && result.exitCode !== 0) result.status = 'warning'
  return JSON.stringify({
    ...result,
    backend: config.location === 'server' ? 'server' : 'local-service',
  })
}

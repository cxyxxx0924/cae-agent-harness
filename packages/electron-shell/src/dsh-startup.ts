import type { ChildProcess } from 'node:child_process'
import http from 'node:http'
import { createServer } from 'node:net'
import { createInterface } from 'node:readline'

export async function checkDshPort(port: number): Promise<void> {
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error('DSH_PORT 必须是 1–65535 之间的整数。')
  }
  await new Promise<void>((resolve, reject) => {
    const server = createServer()
    server.once('error', (error: NodeJS.ErrnoException) => {
      reject(error.code === 'EADDRINUSE'
        ? new Error(`后台端口 ${port} 已被占用。请退出之前启动的 SIMFLOW 或 dsh 后重试。`)
        : error)
    })
    server.listen({ host: '127.0.0.1', port, exclusive: true }, () => {
      server.close(error => error ? reject(error) : resolve())
    })
  })
}

export function waitForDsh(proc: ChildProcess, origin: string, timeoutMs: number): Promise<string> {
  return new Promise((resolve, reject) => {
    if (!proc.stdout) {
      reject(new Error('无法读取 dsh 启动输出。'))
      return
    }
    const output = createInterface({ input: proc.stdout })
    let request: http.ClientRequest | undefined
    let settled = false
    const timeout = setTimeout(() => {
      finish(new Error(`dsh did not start within ${timeoutMs}ms`))
    }, timeoutMs)

    function finish(error?: Error, url?: string): void {
      if (settled) return
      settled = true
      clearTimeout(timeout)
      output.close()
      proc.off('error', onError)
      proc.off('exit', onExit)
      proc.stdout?.off('error', onError)
      request?.destroy()
      if (error) reject(error)
      else resolve(url!)
    }

    function onError(error: Error): void {
      finish(error)
    }

    function onExit(code: number | null, signal: NodeJS.Signals | null): void {
      finish(new Error(`dsh exited before startup completed (${signal ?? code}).`))
    }

    output.on('line', (line: string) => {
      const match = /^dsh web: (http:\/\/\S+)$/.exec(line)
      if (!match || request || settled) return
      let url: URL
      try {
        url = new URL(match[1])
      } catch {
        return
      }
      if (url.origin !== origin || url.pathname !== '/' || !url.searchParams.get('token')) return
      request = http.get(url, response => {
        const authenticated = response.statusCode === 303 && Boolean(response.headers['set-cookie']?.length)
        response.resume()
        if (authenticated) finish(undefined, url.href)
        else finish(new Error(`dsh authentication failed (HTTP ${response.statusCode}).`))
      })
      request.setTimeout(5000, () => request?.destroy(new Error('dsh authentication request timed out.')))
      request.on('error', onError)
    })
    proc.once('error', onError)
    proc.once('exit', onExit)
    proc.stdout.on('error', onError)
    if (proc.exitCode !== null || proc.signalCode !== null) onExit(proc.exitCode, proc.signalCode)
  })
}

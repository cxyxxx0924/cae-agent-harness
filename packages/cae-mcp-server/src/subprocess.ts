import { spawn, type SpawnOptionsWithoutStdio } from 'node:child_process'

export interface RunResult {
  stdout: string
  stderr: string
  exitCode: number
}

export function runProcess(
  executable: string,
  args: string[],
  opts: SpawnOptionsWithoutStdio & { signal?: AbortSignal; timeoutMs?: number } = {},
): Promise<RunResult> {
  return new Promise((resolve, reject) => {
    const { signal, timeoutMs, ...spawnOpts } = opts
    if (signal?.aborted) { reject(new Error('Process cancelled before launch')); return }
    const proc = spawn(executable, args, { ...spawnOpts, shell: false })
    let stdout = ''
    let stderr = ''
    let stopped: Error | undefined
    let killTimer: ReturnType<typeof setTimeout> | undefined
    let timer: ReturnType<typeof setTimeout> | undefined

    proc.stdout.on('data', (chunk: Buffer) => { stdout += chunk.toString() })
    proc.stderr.on('data', (chunk: Buffer) => { stderr += chunk.toString() })

    const stop = (error: Error) => {
      if (stopped) return
      stopped = error
      proc.kill('SIGTERM')
      killTimer = setTimeout(() => proc.kill('SIGKILL'), 3000)
    }
    const onAbort = () => stop(new Error('Process cancelled; check solver output before retrying'))
    signal?.addEventListener('abort', onAbort, { once: true })
    if (signal?.aborted) onAbort()

    if (timeoutMs !== undefined) {
      timer = setTimeout(() => stop(new Error(`Process timed out after ${timeoutMs}ms: ${executable}`)), timeoutMs)
    }

    proc.on('close', (code) => {
      clearTimeout(timer)
      clearTimeout(killTimer)
      signal?.removeEventListener('abort', onAbort)
      if (stopped) reject(stopped)
      else resolve({ stdout, stderr, exitCode: code ?? -1 })
    })

    proc.on('error', (err) => {
      clearTimeout(timer)
      clearTimeout(killTimer)
      signal?.removeEventListener('abort', onAbort)
      reject(err)
    })
  })
}

export function tailLog(text: string, maxChars = 8000): string {
  return text.length > maxChars ? `...[truncated]\n${text.slice(-maxChars)}` : text
}

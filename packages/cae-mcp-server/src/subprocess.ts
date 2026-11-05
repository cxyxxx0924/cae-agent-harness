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
    const proc = spawn(executable, args, { ...spawnOpts, shell: false })
    let stdout = ''
    let stderr = ''

    proc.stdout.on('data', (chunk: Buffer) => { stdout += chunk.toString() })
    proc.stderr.on('data', (chunk: Buffer) => { stderr += chunk.toString() })

    const onAbort = () => { proc.kill('SIGTERM') }
    signal?.addEventListener('abort', onAbort, { once: true })

    let timer: ReturnType<typeof setTimeout> | undefined
    if (timeoutMs !== undefined) {
      timer = setTimeout(() => {
        proc.kill('SIGTERM')
        reject(new Error(`Process timed out after ${timeoutMs}ms: ${executable}`))
      }, timeoutMs)
    }

    proc.on('close', (code) => {
      clearTimeout(timer)
      signal?.removeEventListener('abort', onAbort)
      resolve({ stdout, stderr, exitCode: code ?? -1 })
    })

    proc.on('error', (err) => {
      clearTimeout(timer)
      signal?.removeEventListener('abort', onAbort)
      reject(err)
    })
  })
}

export function tailLog(text: string, maxChars = 8000): string {
  return text.length > maxChars ? `...[truncated]\n${text.slice(-maxChars)}` : text
}

import type { ChildProcess } from 'node:child_process'
import { appendFileSync, mkdirSync, renameSync, statSync } from 'node:fs'
import { dirname } from 'node:path'
import { createInterface } from 'node:readline'

export class RuntimeLog {
  private secrets: string[] = []
  private recent: string[] = []

  constructor(readonly path: string) {}

  setSecrets(values: (string | undefined)[]): void {
    this.secrets = [...new Set([...this.secrets, ...values.filter((value): value is string => Boolean(value))])]
      .sort((a, b) => b.length - a.length)
  }

  redact(text: string): string {
    for (const secret of this.secrets) text = text.split(secret).join('[REDACTED]')
    return text.replace(/([?&]token=)[^\s&#]+/gi, '$1[REDACTED]')
  }

  write(source: string, text: string): void {
    const line = `${new Date().toISOString()} [${source}] ${this.redact(text).trimEnd()}\n`
    this.recent.push(line)
    while (this.recent.join('').length > 8000) this.recent.shift()
    try {
      mkdirSync(dirname(this.path), { recursive: true })
      if (statSize(this.path) > 2 * 1024 * 1024) renameSync(this.path, `${this.path}.previous`)
      appendFileSync(this.path, line, { encoding: 'utf8', mode: 0o600 })
    } catch {
      // Keep the recent output available in the error dialog if the disk is unavailable.
    }
  }

  capture(proc: ChildProcess): void {
    for (const [name, stream] of [['stdout', proc.stdout], ['stderr', proc.stderr]] as const) {
      if (!stream) continue
      // Read complete lines so credentials split between pipe chunks stay redacted.
      const lines = createInterface({ input: stream })
      lines.on('line', line => this.write(`dsh:${name}`, line))
      stream.on('error', error => this.write(`dsh:${name}`, error.message))
    }
  }

  failure(error: unknown): string {
    const message = this.redact(error instanceof Error ? error.message : String(error))
    return `${message}\n\n启动日志：${this.path}\n\n最近的后台输出：\n${this.recent.join('').slice(-6000)}`
  }
}

function statSize(path: string): number {
  try {
    return statSync(path).size
  } catch {
    return 0
  }
}

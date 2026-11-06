import { join } from 'node:path'
import { createReadStream, existsSync } from 'node:fs'
import { createInterface } from 'node:readline'
import { z } from 'zod'
import { CAE_CONFIG } from '../config'
import { runProcess, tailLog } from '../subprocess'
import { solveViaService, usesSolverService, SOLVE_TIMEOUT_MS } from '../solver-service'

export const SolveSchema = z.object({
  keyword_file: z.string().describe('Absolute path to the LS-DYNA .key or .k file. In service mode, the path and all INCLUDE files must be accessible to the solver service.'),
  ncpu: z.number().int().min(1).max(64).default(4).describe('Number of CPU cores'),
  memory: z.string().default('2000m').describe('Solver memory e.g. "2000m" or "4g"'),
  output_dir: z.string().optional().describe('Directory for solver output; defaults to keyword file directory'),
})
export type SolveArgs = z.infer<typeof SolveSchema>

const PROGRESS_RE = /t=\s*([\d.]+)\s+dt=\s*([\d.e+-]+)\s+flush\s+i=\s*(\d+)/i
const TERMTIME_RE = /termination time\s*=\s*([\d.]+)/i

async function extractTerminationTime(keyFile: string): Promise<number | null> {
  try {
    const rl = createInterface({ input: createReadStream(keyFile), crlfDelay: Infinity })
    for await (const line of rl) {
      const m = line.match(TERMTIME_RE)
      if (m) return parseFloat(m[1])
    }
  } catch { /* ignore */ }
  return null
}

export async function solveLsDyna(args: SolveArgs, signal?: AbortSignal): Promise<string> {
  if (usesSolverService(CAE_CONFIG.solver)) return solveViaService(args, CAE_CONFIG.solver, signal)
  if (!CAE_CONFIG.lsdyna) throw new Error('尚未配置本地求解器，请在“设置 → 仿真软件”选择软件或求解服务。')
  if (!existsSync(args.keyword_file)) {
    throw new Error(`Keyword file not found: ${args.keyword_file}`)
  }
  const termTime = await extractTerminationTime(args.keyword_file)
  const outDir = args.output_dir ?? join(args.keyword_file, '..')
  const result = await runProcess(
    CAE_CONFIG.lsdyna,
    [`i=${args.keyword_file}`, `ncpu=${args.ncpu}`, `memory=${args.memory}`],
    { cwd: outDir, timeoutMs: SOLVE_TIMEOUT_MS, signal },
  )
  const log = tailLog(result.stdout + result.stderr)
  if (result.exitCode !== 0 || log.includes('E r r o r') || log.includes('*** Error')) {
    throw new Error(`LS-DYNA solver error (exit ${result.exitCode})\n${log}`)
  }
  const stats: Record<string, unknown> = {}
  if (termTime !== null) stats.terminationTime = termTime
  const progressMatches = [...(result.stdout + result.stderr).matchAll(
    new RegExp(PROGRESS_RE.source, 'gi'),
  )]
  if (progressMatches.length > 0) {
    const last = progressMatches[progressMatches.length - 1]
    stats.lastSimTime = parseFloat(last[1])
    stats.lastTimestep = last[2]
    stats.lastCycle = parseInt(last[3], 10)
  }
  const d3plot = join(outDir, 'd3plot')
  const logFile = join(outDir, 'messag')
  stats.d3plot = existsSync(d3plot) ? d3plot : null
  stats.logFile = existsSync(logFile) ? logFile : null
  return JSON.stringify({ status: result.exitCode === 0 ? 'ok' : 'warning', exitCode: result.exitCode, backend: 'local-software', ...stats, log })
}

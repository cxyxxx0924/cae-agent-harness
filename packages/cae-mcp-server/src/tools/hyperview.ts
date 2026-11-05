import { join } from 'node:path'
import { writeFileSync, existsSync } from 'node:fs'
import { z } from 'zod'
import { CAE_CONFIG } from '../config'
import { runProcess, tailLog } from '../subprocess'

export const ExportGifSchema = z.object({
  d3plot: z.string().describe('Absolute path to the LS-DYNA d3plot result file'),
  output_gif: z.string().optional().describe('Output GIF file path; defaults to <workdir>/result.gif'),
  component: z.string().default('').describe('Component name to isolate (empty = show all)'),
  result_type: z.enum(['displacement', 'stress', 'strain', 'pressure']).default('displacement')
    .describe('Result type to contour'),
  fps: z.number().int().min(1).max(60).default(10).describe('Frames per second for the GIF'),
  start_frame: z.number().int().min(0).default(0).describe('Start frame index'),
  end_frame: z.number().int().optional().describe('End frame index; defaults to last frame'),
  width: z.number().int().default(1280).describe('Image width in pixels'),
  height: z.number().int().default(720).describe('Image height in pixels'),
})
export type ExportGifArgs = z.infer<typeof ExportGifSchema>

const RESULT_MAP: Record<string, string> = {
  displacement: 'Displacement Magnitude',
  stress: 'Element Stress (vonMises)',
  strain: 'Element Strain Energy',
  pressure: 'Nodal Pressure',
}

export async function exportGif(args: ExportGifArgs): Promise<string> {
  if (!existsSync(args.d3plot)) {
    throw new Error(`d3plot not found: ${args.d3plot}`)
  }
  const outputGif = args.output_gif ?? join(CAE_CONFIG.workdir, 'result.gif')
  const tclPath = join(CAE_CONFIG.workdir, '_export_gif.tcl')
  const resultLabel = RESULT_MAP[args.result_type] ?? 'Displacement Magnitude'
  const endFrame = args.end_frame !== undefined ? args.end_frame : -1
  const tcl = `
hwi OpenStack
hwi GetSessionHandle sess
sess GetProjectHandle proj
proj New
proj GetPageHandle page [proj AddPage]
page GetWindowHandle win [page AddWindow "Animation"]
win SetSize ${args.width} ${args.height}
win GetClientHandle client
client GetModelHandle model [client AddModel]
model SetResult "${args.d3plot.replace(/\\/g, '/')}"
model GetResultCtrlHandle resCtrl
resCtrl SetCurrentResult "${resultLabel}"
${args.component ? `
model GetComponentHandle comp
comp SetVisibility Off
set compId [model FindComponent "${args.component}"]
if {$compId >= 0} { model SetCompVisibility $compId On }
` : ''}
set animCtrl [client GetAnimationCtrl]
$animCtrl SetStartFrame ${args.start_frame}
if { ${endFrame} >= 0 } { $animCtrl SetEndFrame ${endFrame} }
$animCtrl SetFrameRate ${args.fps}
client CaptureToGif "${outputGif.replace(/\\/g, '/')}" ${args.fps}
puts "CAE_GIF_OK: ${outputGif.replace(/\\/g, '/')}"
hwi CloseStack
quit
`
  writeFileSync(tclPath, tcl.trim(), 'utf8')
  const result = await runProcess(
    CAE_CONFIG.hyperview,
    ['-tcl', tclPath, '-nographics'],
    { cwd: CAE_CONFIG.workdir, timeoutMs: 300_000 },
  )
  if (result.exitCode !== 0 && !existsSync(outputGif)) {
    throw new Error(`HyperView export failed (exit ${result.exitCode})\n${tailLog(result.stderr || result.stdout)}`)
  }
  return JSON.stringify({ status: 'ok', output_gif: outputGif, log: tailLog(result.stdout) })
}

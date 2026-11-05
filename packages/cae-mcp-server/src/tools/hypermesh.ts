import { join } from 'node:path'
import { writeFileSync, mkdirSync } from 'node:fs'
import { z } from 'zod'
import { CAE_CONFIG } from '../config'
import { runProcess, tailLog } from '../subprocess'

export const ImportIgsSchema = z.object({
  igs_file: z.string().describe('Absolute path to the IGS or IGES geometry file'),
  output_hm: z.string().optional().describe('Output .hm file path; defaults to <workdir>/model.hm'),
  geometry_scale: z.number().default(1.0).describe('Geometry scale factor (default 1.0)'),
})
export type ImportIgsArgs = z.infer<typeof ImportIgsSchema>

export const PartitionAirbagSchema = z.object({
  hm_file: z.string().describe('HyperMesh model file (.hm) to partition'),
  cushion_component: z.string().default('airbag_cushion').describe('Component name for the cushion panel'),
  inflator_component: z.string().default('airbag_inflator').describe('Component name for the inflator side'),
  vent_component: z.string().default('airbag_vent').describe('Component name for the vent holes'),
  output_hm: z.string().optional().describe('Output partitioned model path'),
})
export type PartitionAirbagArgs = z.infer<typeof PartitionAirbagSchema>

export const GenerateMeshSchema = z.object({
  hm_file: z.string().describe('Partitioned HyperMesh model file (.hm)'),
  element_size: z.number().default(5.0).describe('Target element size in mm'),
  element_type: z.enum(['quad', 'tria', 'mixed']).default('quad').describe('Shell element type'),
  quality_warpage: z.number().default(5.0).describe('Max warpage angle in degrees'),
  quality_aspect: z.number().default(5.0).describe('Max aspect ratio'),
  output_hm: z.string().optional().describe('Output meshed model path'),
  output_key: z.string().optional().describe('Output LS-DYNA keyword file path (.key)'),
})
export type GenerateMeshArgs = z.infer<typeof GenerateMeshSchema>

function runHmbatch(tclScript: string, workdir: string): Promise<{ stdout: string; stderr: string; exitCode: number }> {
  return runProcess(CAE_CONFIG.hmbatch, ['-tcl', tclScript, '-nographics'], { cwd: workdir, timeoutMs: 300_000 })
}

export async function importIgs(args: ImportIgsArgs): Promise<string> {
  mkdirSync(CAE_CONFIG.workdir, { recursive: true })
  const outputHm = args.output_hm ?? join(CAE_CONFIG.workdir, 'model.hm')
  const tclPath = join(CAE_CONFIG.workdir, '_import_igs.tcl')

  const tcl = `
set igsFile "${args.igs_file.replace(/\\/g, '/')}"
set outputHm "${outputHm.replace(/\\/g, '/')}"
set scale ${args.geometry_scale}

hm_answernext yes
*geomimport -scale $scale "$igsFile"
*hm_answernext yes
hm_answernext yes
*writefile "$outputHm" 1
puts "CAE_IMPORT_OK: $outputHm"
quit
`
  writeFileSync(tclPath, tcl, 'utf8')
  const result = await runHmbatch(tclPath, CAE_CONFIG.workdir)
  if (result.exitCode !== 0) {
    throw new Error(`HyperMesh import failed (exit ${result.exitCode})\n${tailLog(result.stderr || result.stdout)}`)
  }
  return JSON.stringify({ status: 'ok', output_hm: outputHm, log: tailLog(result.stdout) })
}

export async function partitionAirbag(args: PartitionAirbagArgs): Promise<string> {
  const outputHm = args.output_hm ?? join(CAE_CONFIG.workdir, 'model_partitioned.hm')
  const tclPath = join(CAE_CONFIG.workdir, '_partition.tcl')

  const tcl = `
set hmFile "${args.hm_file.replace(/\\/g, '/')}"
set cushionComp "${args.cushion_component}"
set inflatorComp "${args.inflator_component}"
set ventComp "${args.vent_component}"
set outputHm "${outputHm.replace(/\\/g, '/')}"

*readfile "$hmFile"

*createentity comps name="$cushionComp"
*createentity comps name="$inflatorComp"
*createentity comps name="$ventComp"

*createstopline
puts "CAE_PARTITION_OK"
*writefile "$outputHm" 1
quit
`
  writeFileSync(tclPath, tcl, 'utf8')
  const result = await runHmbatch(tclPath, CAE_CONFIG.workdir)
  if (result.exitCode !== 0) {
    throw new Error(`HyperMesh partition failed (exit ${result.exitCode})\n${tailLog(result.stderr || result.stdout)}`)
  }
  return JSON.stringify({ status: 'ok', output_hm: outputHm, log: tailLog(result.stdout) })
}

export async function generateMesh(args: GenerateMeshArgs): Promise<string> {
  const outputHm = args.output_hm ?? join(CAE_CONFIG.workdir, 'model_meshed.hm')
  const outputKey = args.output_key ?? join(CAE_CONFIG.workdir, 'airbag.key')
  const tclPath = join(CAE_CONFIG.workdir, '_mesh.tcl')

  const tcl = `
set hmFile "${args.hm_file.replace(/\\/g, '/')}"
set elemSize ${args.element_size}
set elemType "${args.element_type}"
set maxWarpage ${args.quality_warpage}
set maxAspect ${args.quality_aspect}
set outputHm "${outputHm.replace(/\\/g, '/')}"
set outputKey "${outputKey.replace(/\\/g, '/')}"

*readfile "$hmFile"

*createmark surfs 1 "all"
*automesh 1 $elemSize 2 1

hm_answernext yes
*checkelems 1 warpage $maxWarpage
*checkelems 1 aspect $maxAspect

*writefile "$outputHm" 1

*createstopline
*export -template "LsDyna" "$outputKey" 1
puts "CAE_MESH_OK"
quit
`
  writeFileSync(tclPath, tcl, 'utf8')
  const result = await runHmbatch(tclPath, CAE_CONFIG.workdir)
  if (result.exitCode !== 0) {
    throw new Error(`HyperMesh mesh failed (exit ${result.exitCode})\n${tailLog(result.stderr || result.stdout)}`)
  }
  return JSON.stringify({ status: 'ok', output_hm: outputHm, output_key: outputKey, log: tailLog(result.stdout) })
}

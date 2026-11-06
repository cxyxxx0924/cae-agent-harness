import { join } from 'node:path'
import { existsSync, readFileSync } from 'node:fs'
import { z } from 'zod'
import PptxGenJS from 'pptxgenjs'
import { CAE_CONFIG } from '../config'

export const GenerateReportSchema = z.object({
  title: z.string().default('气帘仿真分析报告').describe('Report title'),
  project_name: z.string().default('Airbag CAE').describe('Project name'),
  analyst: z.string().default('CAE Agent').describe('Analyst name'),
  gif_path: z.string().optional().describe('Path to simulation GIF file'),
  keyword_file: z.string().optional().describe('LS-DYNA keyword file path'),
  mesh_info: z.object({
    element_count: z.number().optional(),
    node_count: z.number().optional(),
    element_size: z.number().optional(),
    element_type: z.string().optional(),
    quality_summary: z.string().optional(),
  }).optional().describe('Mesh statistics'),
  solver_info: z.object({
    termination_time: z.number().optional().describe('Termination time in ms'),
    last_sim_time: z.number().optional().describe('Last simulation time in ms'),
    ncpu: z.number().optional(),
    status: z.string().optional(),
  }).optional().describe('Solver run information'),
  evidence_summary: z.string().optional().describe('Actual evidence sources and missing assessment inputs; this report is a process summary, not a regulatory verdict.'),
  output_ppt: z.string().optional().describe('Output PPT file path; defaults to <workdir>/report.pptx'),
})
export type GenerateReportArgs = z.infer<typeof GenerateReportSchema>

const BRAND_COLOR = '1F3864'
const ACCENT_COLOR = '2F75B6'
const LIGHT_COLOR = 'D9E1F2'

function formatDate(): string {
  return new Date().toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' })
}

export async function generateReport(args: GenerateReportArgs): Promise<string> {
  const outputPpt = args.output_ppt ?? join(CAE_CONFIG.workdir, 'report.pptx')
  const pptx = new PptxGenJS()
  pptx.layout = 'LAYOUT_WIDE'
  pptx.title = args.title
  pptx.author = args.analyst
  pptx.subject = '气帘仿真分析报告'
  // Slide 1 — Cover
  const cover = pptx.addSlide()
  cover.background = { fill: BRAND_COLOR }
  cover.addText(args.title, {
    x: 0.5, y: 2.2, w: 12, h: 1.4,
    fontSize: 36, bold: true, color: 'FFFFFF', align: 'center',
  })
  cover.addText(args.project_name, {
    x: 0.5, y: 3.8, w: 12, h: 0.7,
    fontSize: 20, color: 'BDD7EE', align: 'center',
  })
  cover.addText(`分析师: ${args.analyst}  |  日期: ${formatDate()}`, {
    x: 0.5, y: 5.2, w: 12, h: 0.5,
    fontSize: 14, color: 'BDD7EE', align: 'center',
  })
  // Slide 2 — Workflow Overview
  const wfSlide = pptx.addSlide()
  wfSlide.addText('仿真工作流程', {
    x: 0.5, y: 0.3, w: 12, h: 0.8,
    fontSize: 28, bold: true, color: BRAND_COLOR,
  })
  const steps = [
    { step: '1', title: '几何导入', desc: '导入 IGS/IGES 格式的气帘几何模型' },
    { step: '2', title: '模型分区', desc: 'BELT / CAVITY / SEAM / TETHER 四分区' },
    { step: '3', title: '网格划分', desc: '按当前项目参数生成网格并执行质量门禁' },
    { step: '4', title: 'LS-DYNA 求解', desc: '显式动力学仿真，气袋充气展开分析' },
    { step: '5', title: '结果后处理', desc: 'HyperView 导出位移/应力云图动画 GIF' },
    { step: '6', title: '报告生成', desc: '自动生成 PowerPoint 分析报告' },
  ]
  steps.forEach((s, i) => {
    const row = Math.floor(i / 3)
    const col = i % 3
    const x = 0.5 + col * 4.2
    const y = 1.4 + row * 2.0
    wfSlide.addShape(pptx.ShapeType.rect, { x, y, w: 3.8, h: 1.6, fill: { color: LIGHT_COLOR }, line: { color: ACCENT_COLOR, width: 1 } })
    wfSlide.addText(`Step ${s.step}: ${s.title}`, { x, y: y + 0.1, w: 3.8, h: 0.5, fontSize: 13, bold: true, color: BRAND_COLOR, align: 'center' })
    wfSlide.addText(s.desc, { x, y: y + 0.65, w: 3.8, h: 0.8, fontSize: 10, color: '404040', align: 'center', wrap: true })
  })
  // Slide 3 — Mesh Statistics
  const meshSlide = pptx.addSlide()
  meshSlide.addText('网格质量统计', {
    x: 0.5, y: 0.3, w: 12, h: 0.8, fontSize: 28, bold: true, color: BRAND_COLOR,
  })
  const meshRows: string[][] = [['指标', '数值']]
  if (args.mesh_info?.element_count !== undefined) meshRows.push(['单元数量', args.mesh_info.element_count.toLocaleString()])
  if (args.mesh_info?.node_count !== undefined) meshRows.push(['节点数量', args.mesh_info.node_count.toLocaleString()])
  if (args.mesh_info?.element_size !== undefined) meshRows.push(['目标网格尺寸', `${args.mesh_info.element_size} mm`])
  if (args.mesh_info?.element_type) meshRows.push(['单元类型', args.mesh_info.element_type])
  if (args.mesh_info?.quality_summary) meshRows.push(['实际质量检查', args.mesh_info.quality_summary])
  if (meshRows.length === 1) meshRows.push(['网格数据', '未提供，需查看实际门禁记录'])
  meshSlide.addTable(meshRows as any, {
    x: 1.5, y: 1.4, w: 10,
    colW: [5, 5],
    border: { color: ACCENT_COLOR },
    fill: { color: 'FFFFFF' },
    fontSize: 13,
  })
  // Slide 4 — Solver Results
  const solverSlide = pptx.addSlide()
  solverSlide.addText('求解结果摘要', {
    x: 0.5, y: 0.3, w: 12, h: 0.8, fontSize: 28, bold: true, color: BRAND_COLOR,
  })
  const solverRows: string[][] = [['参数', '数值']]
  if (args.solver_info?.termination_time !== undefined) solverRows.push(['仿真结束时间', `${args.solver_info.termination_time} ms`])
  if (args.solver_info?.last_sim_time !== undefined) solverRows.push(['最终仿真时间', `${args.solver_info.last_sim_time.toFixed(4)} ms`])
  if (args.solver_info?.ncpu !== undefined) solverRows.push(['CPU 核数', `${args.solver_info.ncpu}`])
  if (args.solver_info?.status !== undefined) solverRows.push(['求解状态', args.solver_info.status === 'ok' ? '正常完成' : args.solver_info.status])
  if (solverRows.length === 1) solverRows.push(['求解数据', '未提供，需查看实际求解记录'])
  solverSlide.addTable(solverRows as any, {
    x: 1.5, y: 1.4, w: 10,
    colW: [5, 5],
    border: { color: ACCENT_COLOR },
    fill: { color: 'FFFFFF' },
    fontSize: 13,
  })
  // Slide 5 — Animation GIF (if provided)
  if (args.gif_path !== undefined && existsSync(args.gif_path)) {
    const gifSlide = pptx.addSlide()
    gifSlide.addText('仿真动画', {
      x: 0.5, y: 0.3, w: 12, h: 0.8, fontSize: 28, bold: true, color: BRAND_COLOR,
    })
    gifSlide.addImage({
      path: args.gif_path,
      x: 1.5, y: 1.2, w: 10, h: 5.6, sizing: { type: 'contain', w: 10, h: 5.6 },
    })
  }
  const evidenceSlide = pptx.addSlide()
  evidenceSlide.addText('证据与评判范围', { x: 0.5, y: 0.3, w: 12, h: 0.8, fontSize: 28, bold: true, color: BRAND_COLOR })
  evidenceSlide.addText(args.evidence_summary || '本报告为仿真过程摘要。未提供法规评价所需的完整测点、坐标对齐和动态保护证据，不能据此判定法规合格。', { x: 0.7, y: 1.5, w: 11.8, h: 4.8, fontSize: 16, color: '404040', breakLine: false, fit: 'shrink' })
  // Closing slide.
  const endSlide = pptx.addSlide()
  endSlide.background = { fill: BRAND_COLOR }
  endSlide.addText('Thank You', {
    x: 0.5, y: 2.5, w: 12, h: 1.2, fontSize: 40, bold: true, color: 'FFFFFF', align: 'center',
  })
  endSlide.addText('由 CAE Agent 自动生成', {
    x: 0.5, y: 4.2, w: 12, h: 0.6, fontSize: 16, color: 'BDD7EE', align: 'center',
  })
  await pptx.writeFile({ fileName: outputPpt })
  return JSON.stringify({ status: 'ok', output_ppt: outputPpt })
}

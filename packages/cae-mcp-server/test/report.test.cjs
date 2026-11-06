const assert = require('node:assert/strict')
const { mkdtemp, rm, readFile } = require('node:fs/promises')
const { tmpdir } = require('node:os')
const { join } = require('node:path')
const { createRequire } = require('node:module')
const { test } = require('node:test')
const { generateReport, GenerateReportSchema } = require('../dist/tools/report.js')
const { zodToJsonSchema } = require('../dist/schema.js')
const JSZip = createRequire(require.resolve('pptxgenjs'))('jszip')

test('report tool exposes nested parameter types to the model', () => {
  const schema = zodToJsonSchema(GenerateReportSchema)
  assert.equal(schema.properties.mesh_info.type, 'object')
  assert.equal(schema.properties.mesh_info.properties.element_size.type, 'number')
  assert.equal(schema.properties.mesh_info.properties.element_type.type, 'string')
  assert.equal(schema.required.includes('mesh_info'), false)
  assert.match(schema.properties.solver_info.properties.termination_time.description, /ms/)
})

test('process report contains supplied mesh values and millisecond units without invented quality results', async t => {
  const directory = await mkdtemp(join(tmpdir(), 'cae-report-'))
  t.after(() => rm(directory, { recursive: true, force: true }))
  const result = JSON.parse(await generateReport(GenerateReportSchema.parse({
    title: 'Current report', analyst: 'Analyst', project_name: 'Current project', output_ppt: join(directory, 'report.pptx'),
    mesh_info: { element_size: 7, element_type: 'mixed', element_count: 900 },
    solver_info: { termination_time: 80, last_sim_time: 80, ncpu: 8, status: 'ok' },
  })))
  const zip = await JSZip.loadAsync(await readFile(result.output_ppt))
  const text = (await Promise.all(Object.keys(zip.files).filter(file => /^ppt\/slides\/slide\d+\.xml$/.test(file)).map(file => zip.file(file).async('string')))).join('\n')
  assert.match(text, /7 mm/)
  assert.match(text, /mixed/)
  assert.match(text, /80 ms/)
  assert.match(text, /不能据此判定法规合格/)
  assert.equal(text.includes('5mm'), false)
  assert.equal(text.includes('SHELL163'), false)
  assert.equal(text.includes('翘曲角'), false)
})

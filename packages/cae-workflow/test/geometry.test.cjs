const assert = require('node:assert/strict')
const fs = require('node:fs')
const { tmpdir } = require('node:os')
const path = require('node:path')
const { spawnSync } = require('node:child_process')
const { test } = require('node:test')
const { partitionGeometryPassed } = require('../gates.cjs')
const python = process.env.PY || (process.platform === 'win32' ? 'python' : 'python3')
const tclsh = process.env.TCLSH || 'tclsh'

test('independent partition readback runs trial geometry and fails on open, overlapping or uncut regions', t => {
  const directory = fs.mkdtempSync(path.join(tmpdir(), 'cae-geometry-'))
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }))
  fs.mkdirSync(path.join(directory, 'out'))
  fs.writeFileSync(path.join(directory, 'out', 'class_lists.tcl'), 'set BELT_N 4\nset CAVITY_N 4\nset SEAM_N 0\nset TETHER_N 0\n')
  const script = path.resolve(__dirname, '../../../docs/气帘iges分区skill/scripts/t08_verify_partitioned.tcl')
  for (const mode of ['valid', 'reversed_cut', 'open', 'overlap', 'no_cut', 'query_error']) {
    const valid = ['valid', 'reversed_cut'].includes(mode)
    const run = spawnSync(tclsh, [path.join(__dirname, 'hypermesh-fixture.tcl'), script, mode, directory], { encoding: 'utf8' })
    assert.equal(run.status, 0, run.stderr)
    const report = JSON.parse(fs.readFileSync(path.join(directory, 'out', 'partition_geometry.json')))
    const counts = fs.readFileSync(path.join(directory, 'out', 'verify_partitioned.txt'), 'utf8')
    assert.match(counts, /COUNT OK/)
    assert.equal(partitionGeometryPassed(report), valid, mode)
    assert.match(counts, valid ? /VERIFY_FAIL=0/ : /VERIFY_FAIL=1/)
    if (valid) {
      assert.equal(report.metrics.belt_area, 3600)
      assert.equal(report.metrics.cavity_area, 6400)
    } else {
      assert.ok(report.failures.length > 0)
      if (mode === 'open') assert.ok(report.raw_free_endpoints.CAVITY.some(endpoint => endpoint.line_ids.includes(8)))
    }
  }
})

test('mesh template stops before meshing when the cavity cut overlaps or fails', t => {
  const directory = fs.mkdtempSync(path.join(tmpdir(), 'cae-mesh-geometry-'))
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }))
  fs.mkdirSync(path.join(directory, 'out'))
  const template = path.resolve(__dirname, '../../../docs/气帘自动网格划分_20261101(1)/气帘自动网格划分/scripts/stage3_mesh/blmesh2d/step1_template.tcl')
  const source = fs.readFileSync(template, 'utf8')
  const guardEnd = source.indexOf('# ===== 4.')
  assert.ok(guardEnd > 0)
  const script = path.join(directory, 'pre_mesh.tcl')
  const replacements = { CASENAME: 'fixture', MODEL: 'partitioned.hm', CID_CAV: '2', CID_BELT: '1', RINGDEFS: '{}' }
  fs.writeFileSync(script, source.slice(0, guardEnd).replace(/@@(\w+)@@/g, (_, key) => replacements[key]) + '\nputs "GEOMETRY_OK belt=[surf_area $SBELT] cavity=[surf_area $SCAV]"\nclose $rep\n')
  for (const mode of ['valid', 'reversed_cut', 'open', 'overlap', 'no_cut']) {
    const run = spawnSync(tclsh, [path.join(__dirname, 'hypermesh-fixture.tcl'), script, mode, directory], { encoding: 'utf8' })
    if (['valid', 'reversed_cut'].includes(mode)) {
      assert.equal(run.status, 0, run.stderr)
      assert.match(run.stdout, /GEOMETRY_OK belt=3600 cavity=6400/)
    } else {
      assert.notEqual(run.status, 0, mode)
      assert.doesNotMatch(run.stdout, /GEOMETRY_OK/)
    }
  }
})

test('existing HM readback must match K coordinates and connectivity', t => {
  const directory = fs.mkdtempSync(path.join(tmpdir(), 'cae-mesh-readback-'))
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }))
  const hm = path.join(directory, 'mesh.hm'), kfile = path.join(directory, 'mesh.k')
  const raw = path.join(directory, 'readback.txt'), report = path.join(directory, 'report.json')
  fs.writeFileSync(hm, 'HM fixture')
  fs.writeFileSync(kfile, '*KEYWORD\n*NODE\n1,0,0,0\n2,5,0,0\n3,5,5,0\n4,0,5,0\n*ELEMENT_SHELL\n1,2,1,2,3,4\n*END\n')
  const data = `HM_FILE ${hm}\nN 1 0 0 0\nN 2 5 0 0\nN 3 5 5 0\nN 4 0 5 0\nE 1 1 2 3 4\nREADBACK_DONE\n`
  const script = path.resolve(__dirname, '../../../docs/气帘自动网格划分_20261101(1)/气帘自动网格划分/scripts/gate/verify_mesh_readback.py')
  for (const [name, input, expected] of [
    ['matching', data, 0],
    ['rotated nodes', data.replace('E 1 1 2 3 4', 'E 1 3 4 1 2'), 0],
    ['coordinates', data.replace('N 3 5 5 0', 'N 3 6 5 0'), 1],
    ['connectivity', data.replace('E 1 1 2 3 4', 'E 1 1 2 3'), 1],
    ['crossed quad', data.replace('E 1 1 2 3 4', 'E 1 1 3 2 4'), 1],
    ['opposite normal', data.replace('E 1 1 2 3 4', 'E 1 4 3 2 1'), 1],
    ['invalid node', data.replace('N 3 5 5 0', 'N 3 5 5'), 1],
    ['wrong source', data.replace(hm, kfile), 1],
    ['incomplete', data.replace('READBACK_DONE', ''), 1],
  ]) {
    fs.writeFileSync(raw, input)
    const run = spawnSync(python, ['-B', script, '--hm', hm, '--k', kfile, '--readback', raw, '--out', report], { encoding: 'utf8' })
    assert.equal(run.status, expected, `${name}: ${run.stderr}`)
    const result = JSON.parse(fs.readFileSync(report))
    assert.equal(result.overall, expected ? 'FAIL' : 'PASS')
    if (!expected) assert.equal(result.elements, 1)
  }
})

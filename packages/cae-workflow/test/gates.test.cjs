const assert = require('node:assert/strict')
const { test } = require('node:test')
const { evidencePassed } = require('../gates.cjs')
const { autoGate } = require('./gate-fixtures.cjs')

test('auto_gate accepts complete PASS and the two documented WARN types', () => {
  for (const warn of [false, true]) assert.equal(evidencePassed('auto_gate', JSON.stringify(autoGate('/project/current.k', warn))), true)
})

test('auto_gate rejects FAIL, unknown WARN, skipped checks and contradictory PASS claims', () => {
  const rejected = [
    report => { report.overall = 'FAIL' },
    report => { report.results[4].status = 'FAIL' },
    report => { report.results[0].detail.push(['hard failure', 1, 'FAIL']) },
    report => { report.results[0].metrics.dup_nodes = 1 },
    report => { report.results[3].metrics.belt.real_fail_lines.push([188, 45.56, 30]) },
    report => { report.results[4].status = 'WARN'; report.results[4].detail.push(['new warning', 1, 'WARN']) },
    report => { report.results[0].detail.push(['unknown warning', 1, 'WARN']) },
    report => { report.results[3].status = 'SKIP' },
    report => { report.results.pop() },
    report => { report.results[0] = report.results[1] },
    report => { report.overall = 'PASS' },
    report => { report.results[0].detail = [] },
  ]
  for (const mutate of rejected) {
    const report = autoGate('/project/current.k', true)
    mutate(report)
    assert.equal(evidencePassed('auto_gate', JSON.stringify(report)), false, mutate.toString())
  }
  for (const text of ['PASS', '{"overall":"WARN","passed":true}', '{"overall":"PASS"}']) assert.equal(evidencePassed('auto_gate', text), false)
  for (const mutate of [
    report => { report.results[0].metrics.dup_nodes = 1 },
    report => { report.results[3].metrics.belt.real_fail_lines = [[188, 45.56, 30]] },
    report => { report.results[1].detail = [] },
  ]) {
    const report = autoGate('/project/current.k')
    mutate(report)
    assert.equal(evidencePassed('auto_gate', JSON.stringify(report)), false, mutate.toString())
  }
})

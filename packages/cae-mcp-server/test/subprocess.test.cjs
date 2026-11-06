const assert = require('node:assert/strict')
const { mkdtemp, rm, readFile } = require('node:fs/promises')
const { join } = require('node:path')
const { tmpdir } = require('node:os')
const { test } = require('node:test')
const { runProcess } = require('../dist/subprocess.js')

test('a timed-out process reaches shutdown before its tool call rejects', async t => {
  const directory = await mkdtemp(join(tmpdir(), 'cae-process-'))
  t.after(() => rm(directory, { recursive: true, force: true }))
  const marker = join(directory, 'stopped.txt')
  const script = `process.on('SIGTERM', () => setTimeout(() => { require('node:fs').writeFileSync(process.argv[1], 'stopped'); process.exit(0) }, 80)); setInterval(() => {}, 1000)`
  if (process.platform === 'win32') {
    await assert.rejects(runProcess(process.execPath, ['-e', script, marker], { timeoutMs: 300 }), /timed out/)
  } else {
    await assert.rejects(runProcess(process.execPath, ['-e', script, marker], { timeoutMs: 300 }), /timed out/)
    assert.equal(await readFile(marker, 'utf8'), 'stopped')
  }
})

test('an already-cancelled solver call does not launch a process', async () => {
  await assert.rejects(runProcess('must-not-launch', [], { signal: AbortSignal.abort() }), /cancelled before launch/)
})

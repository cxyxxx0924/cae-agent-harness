const assert = require('node:assert/strict')
const { lstat, mkdir, mkdtemp, readFile, rm, symlink, writeFile } = require('node:fs/promises')
const { test } = require('node:test')
const { tmpdir } = require('node:os')
const { join } = require('node:path')
const { isNodeScript, materializeSymlinks, pnpmInvocation } = require('../scripts/package-windows.cjs')

test('runs a JavaScript pnpm entrypoint through the current Node executable', () => {
  const invocation = pnpmInvocation('/opt/pnpm/pnpm.cjs')
  assert.deepEqual(invocation, {
    command: process.execPath,
    args: ['/opt/pnpm/pnpm.cjs'],
  })
})

test('runs a native pnpm executable directly instead of passing it to Node', () => {
  const invocation = pnpmInvocation('/Users/rcc/.local/bin/pnpm')
  assert.deepEqual(invocation, {
    command: '/Users/rcc/.local/bin/pnpm',
    args: [],
  })
})

test('recognizes a Node shebang even when the pnpm entrypoint has no extension', () => {
  const file = require('node:os').tmpdir() + `/cae-pnpm-${process.pid}`
  require('node:fs').writeFileSync(file, '#!/usr/bin/env node\n')
  try {
    assert.equal(isNodeScript(file), true)
  } finally {
    require('node:fs').rmSync(file, { force: true })
  }
})

test('materializes package symlinks before the pnpm store is removed', async t => {
  const root = await mkdtemp(join(tmpdir(), 'cae-package-links-'))
  t.after(() => rm(root, { recursive: true, force: true }))
  const target = join(root, 'node_modules', '.pnpm', 'store', 'package.json')
  const link = join(root, 'packages', 'service', 'node_modules', 'package.json')
  await mkdir(join(root, 'node_modules', '.pnpm', 'store'), { recursive: true })
  await mkdir(join(root, 'packages', 'service', 'node_modules'), { recursive: true })
  await writeFile(target, '{"name":"test-package"}\n')
  try {
    await symlink(target, link)
  } catch (error) {
    if (['EACCES', 'EPERM', 'ENOTSUP'].includes(error.code)) {
      t.skip(`symlinks unavailable: ${error.code}`)
      return
    }
    throw error
  }

  await materializeSymlinks(root)
  assert.equal((await lstat(link)).isSymbolicLink(), false)
  assert.equal(await readFile(link, 'utf8'), '{"name":"test-package"}\n')
})

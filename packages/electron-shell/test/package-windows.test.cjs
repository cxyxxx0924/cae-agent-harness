const assert = require('node:assert/strict')
const { lstat, mkdir, mkdtemp, readFile, rm, symlink, writeFile } = require('node:fs/promises')
const { test } = require('node:test')
const { tmpdir } = require('node:os')
const { join } = require('node:path')
const { isNodeScript, materializeSymlinks, pnpmInvocation, verifyDesktopUi, verifyWorkflow, skillAsset } = require('../scripts/package-windows.cjs')

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

test('Windows packaging rejects a desktop UI without its model host or settings startup dependencies', async t => {
  const root = await mkdtemp(join(tmpdir(), 'cae-package-ui-'))
  t.after(() => rm(root, { recursive: true, force: true }))
  const directory = join(root, 'packages', 'cae-ui')
  await mkdir(directory, { recursive: true })
  const manifest = JSON.parse(await readFile(join(__dirname, '../../cae-ui/package.json'), 'utf8'))
  const manifestPath = join(directory, 'package.json')
  await writeFile(manifestPath, JSON.stringify(manifest))
  for (const file of ['index.js', 'client.js']) await writeFile(join(directory, file), '')
  await assert.rejects(verifyDesktopUi(root), /llm\.js/)
  await writeFile(join(directory, 'llm.js'), '')
  await verifyDesktopUi(root)
  manifest.dsh.client.inject = ['@deepseek-ai/dsh-client-ui-settings']
  await writeFile(manifestPath, JSON.stringify(manifest))
  await assert.rejects(verifyDesktopUi(root), /startup dependency/)
})

test('Windows runtime includes the workflow and all canonical skills while excluding archives, logs and datasets', async () => {
  await verifyWorkflow(join(__dirname, '../../..'))
  for (const file of ['docs/.env', 'docs/model.iges', 'docs/skill.rar', 'docs/run.log', 'docs/.venv/settings.json', 'docs/__pycache__/x.pyc', 'docs/datasets/training.json']) assert.equal(skillAsset(file), false, file)
  for (const file of ['docs/skill/SKILL.md', 'docs/skill/scripts/tree_model_v2.json', 'docs/skill/scripts/run_case.sh', 'docs/skill/scripts/t00_import_iges.tcl']) assert.equal(skillAsset(file), true, file)
})

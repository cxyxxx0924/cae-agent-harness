const assert = require('node:assert/strict')
const { execFile } = require('node:child_process')
const { resolve } = require('node:path')
const { test } = require('node:test')
const { promisify } = require('node:util')

const run = promisify(execFile)
const script = String.raw`
  const assert = require('node:assert/strict')
  const { readFileSync } = require('node:fs')
  const { dirname, resolve } = require('node:path')
  const { pathToFileURL } = require('node:url')
  const { SourceTextModule, SyntheticModule } = require('node:vm')
  const entryPath = process.argv[1]
  const adapterPath = process.argv[2]
  const expectedUrl = pathToFileURL(adapterPath, { windows: true }).href
  const config = {}
  const inject = ['llm']
  let imported = false

  async function load(file) {
    const mod = new SourceTextModule(readFileSync(file, 'utf8'), {
      identifier: file,
      initializeImportMeta: meta => {
        meta.resolve = name => {
          assert.equal(name, '@deepseek-ai/dsh/package.json')
          return 'file:///C:/CAE%20Agent/node_modules/@deepseek-ai/dsh/package.json'
        }
      },
      importModuleDynamically: async specifier => {
        assert.equal(specifier, expectedUrl, 'Windows adapter paths must enter the ESM loader as file URLs')
        imported = true
        const adapter = new SyntheticModule(['Config', 'inject', 'apply'], function () {
          this.setExport('Config', config)
          this.setExport('inject', inject)
          this.setExport('apply', () => {})
        })
        await adapter.link(() => {})
        await adapter.evaluate()
        return adapter
      },
    })
    await mod.link(name => {
      if (name.startsWith('.')) return load(resolve(dirname(file), name))
      if (name === 'node:module') return new SyntheticModule(['createRequire'], function () {
        this.setExport('createRequire', () => ({ resolve: name => {
          assert.equal(name, '@deepseek-ai/dsh-llm-pi-ai')
          return adapterPath
        } }))
      })
      if (name === 'node:url') return new SyntheticModule(['pathToFileURL'], function () {
        this.setExport('pathToFileURL', path => pathToFileURL(path, { windows: true }))
      })
      throw new Error('Unexpected dependency: ' + name)
    })
    return mod
  }

  ;(async () => {
    const entry = await load(entryPath)
    await entry.evaluate()
    assert.equal(imported, true)
    assert.equal(entry.namespace.Config, config)
    assert.equal(entry.namespace.inject, inject)
    assert.equal(typeof entry.namespace.apply, 'function')
  })().catch(error => { console.error(error); process.exitCode = 1 })
`

for (const adapterPath of [
  String.raw`C:\SIMFLOW\resources\runtime\node_modules\@deepseek-ai\dsh-llm-pi-ai\lib\index.js`,
  String.raw`D:\仿真软件 #1\resources\runtime\node_modules\@deepseek-ai\dsh-llm-pi-ai\lib\index.js`,
  String.raw`\\workstation\共享目录\SIMFLOW\node_modules\@deepseek-ai\dsh-llm-pi-ai\lib\index.js`,
]) {
  test(`CAE settings host loads with a Windows adapter path: ${adapterPath}`, async () => {
    const result = await run(process.execPath, [
      '--experimental-vm-modules', '-e', script, resolve(__dirname, '../../cae-ui/index.js'), adapterPath,
    ], { timeout: 10_000 })
    assert.equal(result.stdout, '')
  })
}

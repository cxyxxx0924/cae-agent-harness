const assert = require('node:assert/strict')
const { spawn } = require('node:child_process')
const { createHash } = require('node:crypto')
const { createReadStream, createWriteStream, readFileSync } = require('node:fs')
const { chmod, cp, mkdir, readFile, readdir, realpath, rm, stat, writeFile } = require('node:fs/promises')
const { createRequire } = require('node:module')
const { extname, join, resolve, relative } = require('node:path')
const { Readable } = require('node:stream')
const { pipeline } = require('node:stream/promises')
const { build, Platform, Arch } = require('electron-builder')

const shellRoot = resolve(__dirname, '..')
const projectRoot = resolve(shellRoot, '../..')
const buildRoot = join(projectRoot, 'out', 'windows')
const runtimeRoot = join(buildRoot, 'runtime')
const appRoot = join(buildRoot, 'app')
const outputRoot = join(shellRoot, 'dist-app')
const nodeVersion = '24.14.0'
const uvVersion = '0.9.7'
const uvSha256 = '5d250c32d3604e28dbe18dc65c668ff628c53e00dde2c642576e831e4a60da64'
const builderRequire = createRequire(require.resolve('electron-builder'))
const packagerRequire = createRequire(builderRequire.resolve('app-builder-lib'))
const { path7za } = packagerRequire('7zip-bin')
const { SKILLS } = require('../../cae-workflow/fields.cjs')
const workflowFiles = ['index.js', 'client.js', 'fields.cjs', 'state.cjs', 'policy.js', 'gates.cjs', 'mesh-recovery.cjs']

function skillAsset(source) {
  return !source.split(/[\\/]/).some(part => ['__pycache__', '.venv', 'node_modules', '.git', 'datasets', 'dataset', '.env', 'cae-settings.json', 'config.local.yaml'].includes(part))
    && (!extname(source) || ['.md', '.py', '.json', '.tcl', '.sh', '.png', '.svg', '.txt', '.slide'].includes(extname(source).toLowerCase()))
}

function run(command, args, cwd = projectRoot) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { cwd, stdio: 'inherit', env: { ...process.env, CI: '1' } })
    child.once('error', reject)
    child.once('exit', code => code === 0 ? resolve() : reject(new Error(`${command} exited with code ${code}`)))
  })
}

function isNodeScript(file) {
  const extension = extname(file).toLowerCase()
  if (['.js', '.cjs', '.mjs'].includes(extension)) return true
  try {
    const prefix = readFileSync(file).subarray(0, 128).toString('utf8')
    return /^#!.*\bnode(?:\.exe)?\b/i.test(prefix)
  } catch {
    return false
  }
}

function pnpmInvocation(cli = process.env.npm_execpath) {
  if (!cli || !/pnpm/i.test(cli)) return { command: 'pnpm', args: [] }
  // npm_execpath may point to a native pnpm binary. Passing that file to Node
  // makes Node parse its Mach-O/PE bytes as JavaScript and fail immediately.
  return isNodeScript(cli)
    ? { command: process.execPath, args: [cli] }
    : { command: cli, args: [] }
}

function pnpm(args, cwd) {
  const invocation = pnpmInvocation()
  return run(invocation.command, [...invocation.args, ...args], cwd)
}

async function sha256(file) {
  const hash = createHash('sha256')
  for await (const chunk of createReadStream(file)) hash.update(chunk)
  return hash.digest('hex')
}

async function fetchText(url) {
  const response = await fetch(url, { signal: AbortSignal.timeout(30000) })
  if (!response.ok) throw new Error(`Download failed: ${url} (HTTP ${response.status})`)
  return response.text()
}

async function download(url, file, expectedHash) {
  try {
    if (await sha256(file) === expectedHash) return
  } catch (error) {
    if (error.code !== 'ENOENT') throw error
  }
  await mkdir(resolve(file, '..'), { recursive: true })
  console.log(`Downloading ${url}`)
  const response = await fetch(url, { signal: AbortSignal.timeout(300000) })
  if (!response.ok) throw new Error(`Download failed: ${url} (HTTP ${response.status})`)
  await pipeline(Readable.fromWeb(response.body), createWriteStream(file))
  assert.equal(await sha256(file), expectedHash, `Checksum mismatch: ${file}`)
}

async function copyProjectFile(file, destination = join(runtimeRoot, file)) {
  await mkdir(resolve(destination, '..'), { recursive: true })
  await cp(join(projectRoot, file), destination, { recursive: true, filter: source => {
    return !source.split(/[\\/]/).some(part => part === '__pycache__' || part.endsWith('.egg-info'))
  } })
}

async function assertWindowsExecutable(file, allowedMachines = [0x8664]) {
  const bytes = await readFile(file)
  assert.equal(bytes.subarray(0, 2).toString(), 'MZ', `Missing Windows executable: ${file}`)
  const peOffset = bytes.readUInt32LE(0x3c)
  assert.equal(bytes.readUInt32LE(peOffset), 0x4550, `Invalid PE header: ${file}`)
  assert(allowedMachines.includes(bytes.readUInt16LE(peOffset + 4)), `Unexpected Windows architecture: ${file}`)
}

async function removeBinLinks(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const file = join(directory, entry.name)
    if (entry.name === '.bin') await rm(file, { recursive: true, force: true })
    else if (entry.isDirectory()) await removeBinLinks(file)
  }
}

async function materializeSymlinks(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    if (entry.name === '.pnpm' || entry.name === '.bin') continue
    const file = join(directory, entry.name)
    if (entry.isSymbolicLink()) {
      const target = await realpath(file)
      const targetStat = await stat(target)
      await rm(file, { recursive: true, force: true })
      await cp(target, file, { recursive: targetStat.isDirectory(), dereference: true })
    } else if (entry.isDirectory()) {
      await materializeSymlinks(file)
    }
  }
}

async function verifyTree(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const file = join(directory, entry.name)
    assert(!entry.isSymbolicLink(), `Portable archive contains a symlink: ${file}`)
    assert(!['.env', '.env.local', 'cae-settings.json', '.git', 'config.local.yaml'].includes(entry.name), `Private file in bundle: ${file}`)
    if (entry.isDirectory()) await verifyTree(file)
  }
}

async function verifyDesktopUi(runtime) {
  const directory = join(runtime, 'packages', 'cae-ui')
  const manifest = JSON.parse(await readFile(join(directory, 'package.json'), 'utf8'))
  assert.equal(manifest.name, '@cae/dsh-ui', 'Desktop UI module name does not match its client registration')
  assert.equal(manifest.dsh?.client?.platform, 'web', 'Desktop UI must declare a web client')
  for (const dependency of [
    '@deepseek-ai/dsh-client-ui-settings', '@deepseek-ai/dsh-client-ui-settings-general',
    '@deepseek-ai/dsh-client-ui-workspace', '@deepseek-ai/dsh-client-ui-conversation',
  ]) assert(manifest.dsh.client.inject?.includes(dependency), `Desktop UI is missing startup dependency: ${dependency}`)
  for (const file of [manifest.exports?.['.'], manifest.exports?.['./client'], './llm.js']) {
    assert.equal(typeof file, 'string', 'Desktop UI must export both host and client modules')
    assert((await stat(join(directory, file))).isFile(), `Missing desktop UI file: ${file}`)
  }
}

async function verifyWorkflow(runtime) {
  const directory = join(runtime, 'packages', 'cae-workflow')
  const manifest = JSON.parse(await readFile(join(directory, 'package.json'), 'utf8'))
  assert.equal(manifest.name, '@cae/workflow')
  assert(manifest.dsh?.client?.inject?.includes('@deepseek-ai/dsh-client-ui-sidebar-right'), 'Workflow requires the native dsh sidebar')
  for (const file of workflowFiles) assert((await stat(join(directory, file))).isFile(), `Missing workflow module: ${file}`)
  for (const skill of Object.values(SKILLS)) assert((await stat(join(runtime, skill, 'SKILL.md'))).isFile(), `Missing packaged skill: ${skill}`)
  for (const [skill, scripts] of [
    [SKILLS.partition, ['tree_model_v2.json', 't08_verify_partitioned.tcl', 'partition_geometry.tcl']],
    [SKILLS.mesh, ['gate/readback_mesh.tcl', 'gate/verify_mesh_readback.py', 'gate/auto_gate/kio.py']],
  ]) for (const script of scripts) assert((await stat(join(runtime, skill, 'scripts', script))).isFile(), `Missing workflow skill script: ${script}`)
}

async function main() {
  const args = process.argv.slice(2).filter(arg => arg !== '--')
  if (args.length === 1 && ['--help', '-h'].includes(args[0])) {
    console.log('Usage: pnpm dist:win [--all | --zip | --installer]\nDefault: build both Windows x64 ZIP and NSIS installer.')
    return
  }
  assert(args.length <= 1 && (args.length === 0 || ['--all', '--zip', '--installer'].includes(args[0])), 'Use --all, --zip, or --installer; see --help.')
  const targets = args[0] === '--zip' ? ['zip'] : args[0] === '--installer' ? ['nsis'] : ['zip', 'nsis']
  console.log(`Windows x64 targets: ${targets.join(', ')}`)
  if (process.platform !== 'win32') await chmod(path7za, 0o755)
  await pnpm(['build'])
  await rm(runtimeRoot, { recursive: true, force: true })
  await rm(appRoot, { recursive: true, force: true })
  await mkdir(runtimeRoot, { recursive: true })
  const manifest = JSON.parse(await readFile(join(shellRoot, 'package.json'), 'utf8'))

  for (const file of ['package.json', 'pnpm-lock.yaml', 'packages/electron-shell/package.json', 'packages/cae-mcp-server/package.json', 'packages/cae-ui/package.json', 'packages/cae-workflow/package.json']) {
    await copyProjectFile(file)
  }
  // pnpm resolves optional native packages for the host platform unless the
  // target architectures are declared in the runtime manifest. The build
  // runs on macOS as well as Windows, so explicitly retain the Windows x64
  // variants that the packaged application needs.
  const runtimeManifestPath = join(runtimeRoot, 'package.json')
  const runtimeManifest = JSON.parse(await readFile(runtimeManifestPath, 'utf8'))
  runtimeManifest.pnpm = {
    ...(runtimeManifest.pnpm ?? {}),
    supportedArchitectures: {
      ...(runtimeManifest.pnpm?.supportedArchitectures ?? {}),
      os: ['win32'],
      cpu: ['x64'],
    },
  }
  await writeFile(runtimeManifestPath, JSON.stringify(runtimeManifest, null, 2))
  await writeFile(join(runtimeRoot, 'pnpm-workspace.yaml'), [
    'packages:', '  - packages/*',
    '',
  ].join('\n'))
  // nodeLinker is a pnpm config value rather than a workspace manifest key;
  // pass it explicitly so packages are hoisted into the portable runtime.
  await pnpm(['install', '--prod', '--frozen-lockfile', '--ignore-scripts', '--config.node-linker=hoisted'], runtimeRoot)

  // Workspace links are unnecessary at runtime; imports use the real package paths.
  await rm(join(runtimeRoot, 'node_modules', '@cae'), { recursive: true, force: true })
  await rm(join(runtimeRoot, 'node_modules', '.bin'), { recursive: true, force: true })
  // pnpm can leave package links even with nodeLinker=hoisted. Copy their
  // targets before removing .pnpm so the portable Windows archive has no
  // broken symlinks.
  await materializeSymlinks(runtimeRoot)
  await rm(join(runtimeRoot, 'node_modules', '.pnpm'), { recursive: true, force: true })
  await rm(join(runtimeRoot, 'node_modules', '.modules.yaml'), { force: true })
  await rm(join(runtimeRoot, 'packages', 'electron-shell'), { recursive: true, force: true })
  for (const file of ['pnpm-lock.yaml', 'pnpm-workspace.yaml']) await rm(join(runtimeRoot, file))
  const mcpManifest = JSON.parse(await readFile(join(projectRoot, 'packages/cae-mcp-server/package.json'), 'utf8'))
  await writeFile(join(runtimeRoot, 'package.json'), JSON.stringify({
    name: 'cae-agent-runtime', version: manifest.version, private: true, type: 'module',
    dependencies: { ...manifest.dependencies, ...mcpManifest.dependencies },
  }, null, 2))

  for (const file of [
    'config/cae-airbag.cordis.yml', 'config/config.yaml', 'config/airbag-defaults.yaml',
    'skills', 'packages/cae-mcp-server/dist',
    'packages/cae-ui/index.js', 'packages/cae-ui/client.js', 'packages/cae-ui/llm.js',
  ]) await copyProjectFile(file)
  for (const file of workflowFiles) await copyProjectFile(`packages/cae-workflow/${file}`)
  for (const skill of Object.values(SKILLS)) await cp(join(projectRoot, skill), join(runtimeRoot, skill), { recursive: true, filter: skillAsset })
  for (const project of ['hyperworks-mcp', 'qilan-solve']) {
    for (const file of ['pyproject.toml', 'uv.lock', 'src']) await copyProjectFile(`packages/${project}/${file}`)
  }
  await copyProjectFile('packages/qilan-solve/scripts')

  const nodeBase = `https://nodejs.org/dist/v${nodeVersion}`
  const sums = await fetchText(`${nodeBase}/SHASUMS256.txt`)
  const nodeHash = sums.split('\n').find(line => line.endsWith('  win-x64/node.exe'))?.split(/\s+/)[0]
  assert(nodeHash, 'Node.js Windows checksum was not found')
  const cacheRoot = join(buildRoot, 'cache')
  const nodeCache = join(cacheRoot, `node-v${nodeVersion}-win-x64.exe`)
  await download(`${nodeBase}/win-x64/node.exe`, nodeCache, nodeHash)
  await mkdir(join(runtimeRoot, 'node'), { recursive: true })
  await cp(nodeCache, join(runtimeRoot, 'node', 'node.exe'))
  await writeFile(join(runtimeRoot, 'node', 'LICENSE'), await fetchText(`https://raw.githubusercontent.com/nodejs/node/v${nodeVersion}/LICENSE`))
  const uvZip = join(cacheRoot, `uv-${uvVersion}-win-x64.zip`)
  await download(`https://github.com/astral-sh/uv/releases/download/${uvVersion}/uv-x86_64-pc-windows-msvc.zip`, uvZip, uvSha256)
  await run(path7za, ['x', uvZip, `-o${join(runtimeRoot, 'uv')}`, '-y'])
  await writeFile(join(runtimeRoot, 'uv', 'LICENSE-MIT'), await fetchText(`https://raw.githubusercontent.com/astral-sh/uv/${uvVersion}/LICENSE-MIT`))
  await writeFile(join(runtimeRoot, 'uv', 'LICENSE-APACHE'), await fetchText(`https://raw.githubusercontent.com/astral-sh/uv/${uvVersion}/LICENSE-APACHE`))

  await mkdir(appRoot, { recursive: true })
  await writeFile(join(appRoot, 'package.json'), JSON.stringify({
    name: manifest.name, version: manifest.version, description: manifest.description,
    private: true, type: manifest.type, main: manifest.main,
  }, null, 2))
  await cp(join(shellRoot, 'dist'), join(appRoot, 'dist'), { recursive: true })
  await cp(join(shellRoot, 'resources'), join(appRoot, 'resources'), { recursive: true })
  await removeBinLinks(runtimeRoot)
  await verifyTree(runtimeRoot)
  await verifyDesktopUi(runtimeRoot)
  await verifyWorkflow(runtimeRoot)
  for (const file of [
    'node/node.exe', 'uv/uv.exe',
    'node_modules/node-addon-require-builtin-win32-x64-msvc/prebuilt/win32-x64-msvc-napi-v9.node',
    'node_modules/node-pty/prebuilds/win32-x64/conpty.node',
    'node_modules/@koromix/koffi-win32-x64/win32_x64/koffi.node',
    'node_modules/@vscode/ripgrep-win32-x64/bin/rg.exe',
    'node_modules/@img/sharp-win32-x64/lib/sharp-win32-x64-0.35.5.node',
  ]) await assertWindowsExecutable(join(runtimeRoot, file))

  const artifacts = await build({
    targets: Platform.WINDOWS.createTarget(targets, Arch.x64),
    projectDir: shellRoot,
    config: {
      appId: 'com.cae.agent', productName: 'CAE Agent',
      electronVersion: manifest.devDependencies.electron,
      directories: { app: appRoot, output: outputRoot },
      files: ['dist/**/*', 'resources/**/*'],
      extraResources: [{ from: runtimeRoot, to: 'runtime' }],
      extraFiles: [{ from: join(shellRoot, 'resources', 'windows-README.txt'), to: '使用说明.txt' }],
      npmRebuild: false,
      win: {
        target: targets, icon: join(shellRoot, 'resources', 'icon.ico'),
        signAndEditExecutable: false,
        artifactName: 'CAE-Agent-${version}-Windows-x64.${ext}',
      },
    },
  })
  const packages = artifacts.filter(file => file.endsWith('.zip') || file.endsWith('.exe'))
  for (const target of targets) {
    assert(packages.some(file => file.endsWith(target === 'zip' ? '.zip' : '-Setup.exe')), `Missing ${target} artifact`)
  }
  for (const file of packages) {
    // NSIS uses a 32-bit bootstrap to install the x64 application.
    if (file.endsWith('.exe')) await assertWindowsExecutable(file, [0x14c, 0x8664])
    await run(path7za, ['t', file])
    const digest = await sha256(file)
    await writeFile(`${file}.sha256`, `${digest}  ${relative(outputRoot, file)}\n`)
    console.log(`Created ${file} (${Math.round((await stat(file)).size / 1024 / 1024)} MiB)`)
  }
}

module.exports = { isNodeScript, materializeSymlinks, pnpmInvocation, verifyDesktopUi, verifyWorkflow, skillAsset }

if (require.main === module) main().catch(error => { console.error(error); process.exitCode = 1 })

(() => {
  const storageKey = 'cae-workflow-software-settings-v1'
  const defaults = {
    hmbatch: '', lsdyna: '', solverLocation: 'local', localSolverType: 'software',
    solverLocalServiceUrl: '', solverServerUrl: '',
  }
  let settings = { ...defaults }
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey) || '{}')
    for (const key of Object.keys(defaults)) {
      if (typeof saved?.[key] === 'string') settings[key] = saved[key].trim()
    }
    if (!['local', 'server'].includes(settings.solverLocation)) settings.solverLocation = 'local'
    if (!['software', 'service'].includes(settings.localSolverType)) settings.localSolverType = 'software'
  } catch { /* Use empty settings when browser storage is unavailable or corrupt. */ }

  let backdrop
  let previousFocus
  let previousOverflow
  let requirement
  const field = id => document.getElementById(`software-${id}`)

  function solverField(values) {
    if (values.solverLocation === 'server') return 'solverServerUrl'
    return values.localSolverType === 'service' ? 'solverLocalServiceUrl' : 'lsdyna'
  }

  function missingConfiguration(kind, values) {
    const id = kind === 'hypermesh' ? 'hmbatch' : solverField(values)
    if (values[id]) return null
    const label = id === 'hmbatch' ? 'HyperMesh 批处理程序路径' : id === 'lsdyna' ? 'LS-DYNA 求解器路径' : id === 'solverServerUrl' ? '服务端求解地址' : '本地求解服务地址'
    return { id, message: `尚未配置${label}。请先在“设置 → 仿真软件”完成配置，再继续${kind === 'hypermesh' ? '导入 IGS' : '提交求解'}。已选文件和当前流程会保留。` }
  }

  function close() {
    backdrop.hidden = true
    document.body.style.overflow = previousOverflow
    if (previousFocus?.isConnected) previousFocus.focus()
  }

  function updateModes() {
    const server = field('solverLocation').value === 'server'
    const service = server || field('localSolverType').value === 'service'
    field('localSolverType').closest('.software-settings-field').hidden = server
    field('lsdyna').closest('.software-settings-field').hidden = service
    field('solverLocalServiceUrl').closest('.software-settings-field').hidden = !service || server
    field('solverServerUrl').closest('.software-settings-field').hidden = !server
  }

  function changeMode() {
    updateModes()
    if (requirement !== 'solver') return
    const values = Object.fromEntries(Object.keys(defaults).map(id => [id, field(id).value.trim()]))
    const missing = missingConfiguration('solver', values)
    field('settings-message').textContent = missing?.message || '请核对当前求解方式的配置，保存后返回流程。'
    field('settings-message').dataset.error = 'false'
    if (missing) field(missing.id).focus()
  }

  function buildDialog() {
    backdrop = document.createElement('div')
    backdrop.className = 'software-settings-backdrop'
    backdrop.hidden = true
    backdrop.innerHTML = `
      <section class="software-settings-dialog" role="dialog" aria-modal="true" aria-labelledby="software-settings-title" aria-describedby="software-settings-message">
        <header class="software-settings-head"><h2 id="software-settings-title"><span>设置 / </span>仿真软件</h2><button type="button" class="software-settings-close" data-close aria-label="关闭仿真软件设置">&times;</button></header>
        <form novalidate>
          <div class="software-settings-body">
            <p class="software-settings-notice" id="software-settings-message" role="status"></p>
            <h3>前处理 · HyperMesh</h3>
            <div class="software-settings-field"><label for="software-hmbatch">HyperMesh 批处理程序路径</label><input id="software-hmbatch" type="text" placeholder="C:\\Altair\\2023\\hwdesktop\\hw\\bin\\win64\\hmbatch.exe" aria-describedby="software-hmbatch-hint"><p id="software-hmbatch-hint">填写已安装的 hmbatch.exe 完整路径，用于 IGS 导入、分区和网格划分。</p></div>
            <h3>求解器</h3>
            <div class="software-settings-modes">
              <div class="software-settings-field"><label for="software-solverLocation">求解位置</label><select id="software-solverLocation"><option value="local">本地</option><option value="server">服务端</option></select></div>
              <div class="software-settings-field"><label for="software-localSolverType">本地求解方式</label><select id="software-localSolverType"><option value="software">软件</option><option value="service">求解服务</option></select></div>
            </div>
            <div class="software-settings-field"><label for="software-lsdyna">LS-DYNA 求解器路径</label><input id="software-lsdyna" type="text" placeholder="C:\\LSTC\\lsdyna.exe" aria-describedby="software-lsdyna-hint"><p id="software-lsdyna-hint">填写当前电脑上已安装的 LS-DYNA 可执行文件完整路径。</p></div>
            <div class="software-settings-field" hidden><label for="software-solverLocalServiceUrl">本地求解服务地址</label><input id="software-solverLocalServiceUrl" type="url" placeholder="http://127.0.0.1:8000" aria-describedby="software-local-service-hint"><p id="software-local-service-hint">连接本机已部署的求解服务。</p></div>
            <div class="software-settings-field" hidden><label for="software-solverServerUrl">服务端求解地址</label><input id="software-solverServerUrl" type="url" placeholder="https://solver.example.com" aria-describedby="software-server-hint"><p id="software-server-hint">模型及其引用文件需能被求解服务访问。</p></div>
            <p class="software-settings-note">交互原型 · 配置保存在当前浏览器，仅用于演示配置引导。</p>
          </div>
          <footer class="software-settings-footer"><button type="button" data-close>暂不配置</button><button type="submit">保存并返回流程</button></footer>
        </form>
      </section>`
    document.body.append(backdrop)
    backdrop.querySelectorAll('[data-close]').forEach(button => button.addEventListener('click', close))
    backdrop.addEventListener('click', event => { if (event.target === backdrop) close() })
    backdrop.addEventListener('keydown', event => {
      if (event.key === 'Escape') { event.preventDefault(); close() }
      if (event.key !== 'Tab') return
      const controls = [...backdrop.querySelectorAll('button,input,select')].filter(control => control.getClientRects().length)
      const first = controls[0], last = controls[controls.length - 1]
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    })
    field('solverLocation').addEventListener('change', changeMode)
    field('localSolverType').addEventListener('change', changeMode)
    backdrop.querySelector('form').addEventListener('submit', event => {
      event.preventDefault()
      const values = Object.fromEntries(Object.keys(defaults).map(id => [id, field(id).value.trim()]))
      const missing = requirement ? missingConfiguration(requirement, values) : null
      const active = solverField(values)
      let invalidUrl = false
      if (active !== 'lsdyna' && values[active]) {
        try {
          const endpoint = new URL(values[active])
          invalidUrl = !/^https?:\/\//i.test(values[active]) || /\s/.test(values[active]) || !['http:', 'https:'].includes(endpoint.protocol) || Boolean(endpoint.username || endpoint.password || endpoint.search || endpoint.hash)
        } catch { invalidUrl = true }
      }
      if (missing || invalidUrl) {
        const id = missing?.id || active
        field('settings-message').textContent = missing?.message || '请填写完整的 http:// 或 https:// 求解服务地址；地址中不能包含账号、密码、查询参数或片段。'
        field('settings-message').dataset.error = 'true'
        field(id).setAttribute('aria-invalid', 'true')
        field(id).focus()
        return
      }
      try { localStorage.setItem(storageKey, JSON.stringify(values)) } catch {
        field('settings-message').textContent = '浏览器无法保存配置，请允许本站使用本地存储后重试。'
        field('settings-message').dataset.error = 'true'
        return
      }
      settings = values
      close()
      window.dispatchEvent(new CustomEvent('cae-workflow-settings-saved', { detail: { requirement } }))
    })
  }

  function open(kind) {
    if (!backdrop) buildDialog()
    requirement = kind
    previousFocus = document.activeElement
    previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    for (const id of Object.keys(defaults)) {
      field(id).value = settings[id]
      field(id).removeAttribute('aria-invalid')
    }
    updateModes()
    const missing = kind ? missingConfiguration(kind, settings) : null
    field('settings-message').textContent = missing?.message || '配置 HyperMesh 和当前选用的求解方式。保存后返回当前流程，再继续操作。'
    field('settings-message').dataset.error = 'false'
    backdrop.hidden = false
    field(missing?.id || 'hmbatch').focus()
  }

  window.caeWorkflowSettings = {
    open,
    require(kind) {
      if (!missingConfiguration(kind, settings)) return true
      open(kind)
      return false
    },
  }
  document.querySelectorAll('[data-software-settings]').forEach(button => button.addEventListener('click', () => open()))
})()

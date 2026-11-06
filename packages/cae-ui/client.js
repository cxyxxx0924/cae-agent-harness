window.__ModuleLoader__.load({
  id: '@cae/dsh-ui',
  factory: require => {
    const { createElement, useEffect, useState } = require('react')
    const fields = [
      { id: 'hyperworksHome', label: 'HyperWorks 安装目录', kind: 'directory', placeholder: 'C:\\Altair\\2023', hint: 'HyperMesh、HyperView 等工具共用的 Altair 安装根目录。' },
      { id: 'hmbatch', label: 'HyperMesh 批处理程序', kind: 'file', placeholder: 'C:\\Altair\\2023\\hwdesktop\\hw\\bin\\win64\\hmbatch.exe', hint: '用于几何导入、模型分区和网格划分。' },
      { id: 'hyperview', label: 'HyperView 程序', kind: 'file', placeholder: 'C:\\Altair\\2023\\hwdesktop\\hw\\bin\\win64\\hw.exe', hint: '用于后处理和仿真动画导出。' },
      { id: 'lsdyna', label: 'LS-DYNA 求解器', kind: 'file', placeholder: 'C:\\LSTC\\lsdyna.exe', hint: '选择当前机器安装的 LS-DYNA 可执行文件。' },
      { id: 'workdir', label: '仿真工作目录', kind: 'directory', placeholder: 'D:\\cae_projects\\airbag', hint: '存放几何、网格、求解结果和报告的默认目录。' },
    ]
    const element = createElement

    function CacheSettings() {
      const api = window.caeDesktop
      const [busy, setBusy] = useState(false)
      const [message, setMessage] = useState('')
      const [failed, setFailed] = useState(false)

      async function clearCache() {
        if (busy) return
        setBusy(true)
        setMessage('')
        setFailed(false)
        try {
          const cleared = await api.clearCache()
          if (cleared) setMessage('缓存已清除，正在刷新…')
        } catch (error) {
          setMessage(error instanceof Error ? error.message : '清除缓存失败，请重试。')
          setFailed(true)
        } finally {
          setBusy(false)
        }
      }

      return element('section', { className: 'cae-simulation-settings', 'aria-labelledby': 'cae-cache-title' },
        element('h2', { id: 'cae-cache-title' }, '缓存'),
        element('p', { className: 'cae-settings-intro' }, '设置入口缺失或界面显示异常时，可清除缓存并重新加载界面。'),
        element('p', { className: 'cae-settings-note' }, '已保存的模型配置、仿真软件设置、对话记录和文件会保留。刷新会丢失未保存的输入，请先保存需要的内容。'),
        !api ? element('p', { role: 'status' }, '请在 CAE Agent 桌面应用中清除缓存。') :
          element('div', { className: 'cae-settings-actions' },
            element('button', { type: 'button', disabled: busy, onClick: () => void clearCache() }, busy ? '正在清除…' : '清除缓存并刷新'),
          ),
        element('p', { role: failed ? 'alert' : 'status', className: 'cae-settings-message', 'data-failed': failed }, message),
      )
    }

    function ModelSettings() {
      const api = window.caeModels
      const [values, setValues] = useState(null)
      const [busy, setBusy] = useState(false)
      const [message, setMessage] = useState('')
      const [failed, setFailed] = useState(false)
      const [search, setSearch] = useState('')
      const [onlySelected, setOnlySelected] = useState(false)
      const [checks, setChecks] = useState({})

      useEffect(() => {
        if (!api) return
        let active = true
        api.load().then(settings => {
          if (active) setValues(settings)
        }).catch(() => {
          if (!active) return
          setMessage('读取模型配置失败，请关闭设置后重试。')
          setFailed(true)
        })
        return () => { active = false }
      }, [])

      async function run(operation) {
        if (busy) return
        setBusy(true)
        setMessage('')
        setFailed(false)
        try {
          await operation()
        } catch (error) {
          setMessage(error instanceof Error ? error.message : '操作失败，请重试。')
          setFailed(true)
        } finally {
          setBusy(false)
        }
      }

      function select(models) {
        setValues(previous => ({ ...previous, models, model: models.includes(previous.model) ? previous.model : models[0] || '' }))
        setMessage('')
      }

      function update(id, value) {
        setValues(previous => ({ ...previous, [id]: value, models: [], availableModels: [], model: '' }))
        setChecks({})
        setMessage('接口配置已修改，请重新获取模型列表。')
      }

      function field(id, label, type, placeholder, hint) {
        return element('div', { className: 'cae-settings-field' },
          element('label', { htmlFor: `cae-${id}` }, label),
          element('div', { className: 'cae-settings-input-row' }, element('input', {
            id: `cae-${id}`, type, value: values[id], placeholder,
            autoComplete: 'off', spellCheck: false,
            'aria-describedby': `cae-${id}-hint`,
            onChange: event => update(id, event.target.value),
          })),
          element('p', { id: `cae-${id}-hint`, className: 'cae-settings-hint' }, hint),
        )
      }

      async function discover() {
        setMessage('正在获取模型列表…')
        const discovered = await api.discover(values)
        const selected = values.models.filter(id => discovered.includes(id))
        const removed = values.availableModels.filter(id => !discovered.includes(id)).length
        setValues(previous => ({
          ...previous, availableModels: discovered, models: selected,
          model: selected.includes(previous.model) ? previous.model : selected[0] || '',
        }))
        setChecks({})
        setSearch('')
        setOnlySelected(false)
        setMessage(`已获取 ${discovered.length} 个模型${removed ? `，已移除 ${removed} 个接口不再提供的模型` : ''}。点击模型标签选择要使用的模型。`)
      }

      async function testSelected() {
        setMessage('正在测试已选模型…')
        const results = await api.test(values)
        const unavailable = new Set(results.filter(result => result.status === 'unavailable').map(result => result.id))
        const selected = values.models.filter(id => !unavailable.has(id))
        setValues(previous => ({
          ...previous, models: selected,
          availableModels: previous.availableModels.filter(id => !unavailable.has(id)),
          model: selected.includes(previous.model) ? previous.model : selected[0] || '',
        }))
        setChecks(previous => ({ ...previous, ...Object.fromEntries(results.map(result => [result.id, result])) }))
        const passed = results.filter(result => result.status === 'available').length
        const unknown = results.filter(result => result.status === 'unknown').length
        setMessage(`测试通过 ${passed} 个，移除不可用模型 ${unavailable.size} 个${unknown ? `，${unknown} 个暂时无法确认并保留` : ''}。`)
      }

      const visible = values?.availableModels.filter(id => (!onlySelected || values.models.includes(id)) && id.toLowerCase().includes(search.toLowerCase())) || []
      return element('section', { className: 'cae-simulation-settings', 'aria-labelledby': 'cae-models-title' },
        element('h2', { id: 'cae-models-title' }, '模型'),
        element('p', { className: 'cae-settings-intro' }, '获取当前接口的模型列表，点击标签选择要使用的模型，再选择默认模型。保存后可在对话中切换。'),
        !api ? element('p', { role: 'status' }, '请在 CAE Agent 桌面应用中配置模型。如果已在桌面应用中，请通过“视图 → 清除缓存并刷新”恢复后重试。') :
          !values ? element('p', { role: failed ? 'alert' : 'status' }, message || '正在读取模型配置…') :
            element('form', { onSubmit: event => {
              event.preventDefault()
              void run(async () => {
                await api.save(values)
                setMessage('已保存，正在重启后台服务…')
              })
            } },
              element('fieldset', { disabled: busy },
                field('apiKey', 'API Key', 'password', values.hasApiKey ? '已保存，留空保留原密钥' : 'sk-…', '当前接口的访问密钥；本地 Ollama 可填写 ollama。'),
                field('llmBaseUrl', 'API Base URL', 'url', 'https://api.deepseek.com/v1', '留空使用 DeepSeek。下方模型共用此接口和 API Key。'),
                element('div', { className: 'cae-settings-field' },
                  element('div', { className: 'cae-model-heading' },
                    element('strong', { id: 'cae-model-list-title' }, '模型列表'),
                    element('button', { type: 'button', onClick: () => void run(discover) }, values.availableModels.length ? '重新获取模型' : '获取模型列表'),
                  ),
                  values.availableModels.length > 0 && element('div', { className: 'cae-model-toolbar' },
                    element('button', { type: 'button', onClick: () => select([...values.availableModels]) }, '全选'),
                    element('button', { type: 'button', onClick: () => select([]) }, '全不选'),
                    element('button', { type: 'button', 'aria-pressed': onlySelected, onClick: () => setOnlySelected(previous => !previous) }, '仅看已选'),
                    element('span', { className: 'cae-model-count' }, `已选 ${values.models.length} / ${values.availableModels.length}`),
                  ),
                  values.availableModels.length > 8 && element('div', { className: 'cae-settings-input-row cae-model-search' }, element('input', {
                    type: 'search', value: search, placeholder: '搜索模型', 'aria-label': '搜索模型',
                    onChange: event => setSearch(event.target.value),
                  })),
                  element('div', { className: 'cae-model-list', role: 'group', 'aria-labelledby': 'cae-model-list-title' },
                    ...visible.map(id => element('button', {
                      key: id, type: 'button', className: 'cae-model-chip', 'aria-pressed': values.models.includes(id),
                      title: checks[id]?.message || id,
                      onClick: () => select(values.models.includes(id) ? values.models.filter(model => model !== id) : [...values.models, id]),
                    }, values.models.includes(id) ? '✓ ' : '+ ', id, checks[id] && element('small', null, checks[id].status === 'available' ? '可用' : '待确认'))),
                    !visible.length && element('p', { className: 'cae-model-empty' }, values.availableModels.length ? '没有符合条件的模型。' : '填写接口地址和 API Key 后，点击“获取模型列表”。'),
                  ),
                  element('div', { className: 'cae-model-test-row' },
                    element('button', { type: 'button', disabled: !values.models.length || values.models.length > 50, onClick: () => void run(testSelected) }, '测试已选'),
                    element('span', { className: 'cae-settings-hint' }, '发送简短请求，可能产生少量用量；每次最多 50 个。'),
                  ),
                  element('p', { className: 'cae-settings-hint' }, '重新获取会移除接口不再提供的模型；测试会移除明确不可用的模型。临时连接失败的模型会保留。'),
                  Object.values(checks).filter(result => result.status !== 'available').map(result => element('p', { key: result.id, className: 'cae-settings-hint' }, `${result.id}：${result.message}`)),
                ),
                element('div', { className: 'cae-settings-field' },
                  element('label', { htmlFor: 'cae-model' }, '默认模型'),
                  element('div', { className: 'cae-settings-input-row' }, element('select', {
                    id: 'cae-model', value: values.models.includes(values.model) ? values.model : '', disabled: !values.models.length,
                    onChange: event => setValues(previous => ({ ...previous, model: event.target.value })),
                  }, !values.models.length && element('option', { value: '' }, '请先选择要使用的模型'),
                  ...values.models.map(id => element('option', { key: id, value: id }, id)))),
                  element('p', { className: 'cae-settings-hint' }, '新对话默认使用此模型；只有已选模型会出现在对话菜单中。'),
                ),
                element('div', { className: 'cae-settings-actions' },
                  element('button', { type: 'submit', className: 'cae-settings-primary', disabled: !values.models.length }, busy ? '处理中…' : '保存并重启'),
                ),
              ),
              element('p', { role: failed ? 'alert' : 'status', className: 'cae-settings-message', 'data-failed': failed }, message),
            ),
      )
    }

    function SimulationSettings() {
      const api = window.caeSimulation
      const [values, setValues] = useState(null)
      const [checks, setChecks] = useState({})
      const [busy, setBusy] = useState(false)
      const [message, setMessage] = useState('')
      const [failed, setFailed] = useState(false)
      const [serviceCheck, setServiceCheck] = useState(null)

      useEffect(() => {
        if (!api) return
        let active = true
        api.load().then(settings => {
          if (active) setValues(settings)
        }).catch(() => {
          if (active) {
            setMessage('读取配置失败，请关闭设置后重试。')
            setFailed(true)
          }
        })
        return () => { active = false }
      }, [])

      async function run(operation) {
        setBusy(true)
        setMessage('')
        setFailed(false)
        try {
          await operation()
        } catch (error) {
          setMessage(error instanceof Error ? error.message : '操作失败，请重试。')
          setFailed(true)
        } finally {
          setBusy(false)
        }
      }

      function update(id, value) {
        setValues(previous => ({ ...previous, [id]: value }))
        setChecks(previous => ({ ...previous, [id]: undefined }))
        setServiceCheck(null)
        setMessage('')
      }

      function pathField(field) {
        return element('div', { key: field.id, className: 'cae-settings-field' },
          element('label', { htmlFor: `cae-${field.id}` }, field.label),
          element('div', { className: 'cae-settings-input-row' },
            element('input', {
              id: `cae-${field.id}`,
              type: 'text',
              value: values[field.id] || '',
              placeholder: field.placeholder,
              'aria-describedby': `cae-${field.id}-hint`,
              onChange: event => update(field.id, event.target.value),
            }),
            element('button', {
              type: 'button',
              'aria-label': `选择${field.label}`,
              onClick: () => void run(async () => {
                const selected = await api.browse(field.kind, field.label)
                if (selected) update(field.id, selected)
              }),
            }, '浏览…'),
          ),
          element('p', { id: `cae-${field.id}-hint`, className: 'cae-settings-hint' }, field.hint),
          checks[field.id] && element('p', { className: 'cae-settings-path-status', 'data-valid': checks[field.id].empty ? undefined : checks[field.id].valid }, checks[field.id].message),
        )
      }

      function choices(id, label, options) {
        return element('fieldset', { className: 'cae-settings-choices' },
          element('legend', null, label),
          element('div', { className: 'cae-settings-choice-row' }, ...options.map(option =>
            element('label', { key: option.value, className: 'cae-settings-choice', 'data-selected': values[id] === option.value },
              element('input', {
                type: 'radio', name: id, value: option.value,
                checked: values[id] === option.value,
                onChange: () => update(id, option.value),
              }),
              element('span', null, element('strong', null, option.label), element('small', null, option.hint)),
            ),
          )),
        )
      }

      const server = values?.solverLocation === 'server'
      const service = server || values?.localSolverType === 'service'
      const urlField = server ? 'solverServerUrl' : 'solverLocalServiceUrl'
      const tokenField = server ? 'solverServerToken' : 'solverLocalServiceToken'

      return element('section', { className: 'cae-simulation-settings', 'aria-labelledby': 'cae-simulation-title' },
        element('h2', { id: 'cae-simulation-title' }, '仿真软件'),
        element('p', { className: 'cae-settings-intro' }, '选择求解位置和接入方式，配置仿真软件与工作目录，保存后自动重启后台服务。'),
        element('p', { className: 'cae-settings-note' }, '仅使用助手时，仿真软件路径可以留空。使用服务端求解时，本机无需安装求解器；几何处理和后处理仍使用下方配置的软件。'),
        !api ? element('p', { role: 'status' }, '请在 CAE Agent 桌面应用中打开“设置 → 仿真软件”配置本机路径。') :
          !values ? element('p', { role: 'status' }, message || '正在读取配置…') :
            element('form', {
              onSubmit: event => {
                event.preventDefault()
                if (busy) return
                void run(async () => {
                  await api.save(values)
                  setMessage('已保存，正在重启后台服务…')
                })
              },
            },
            element('fieldset', { disabled: busy },
              element('div', { className: 'cae-settings-group' },
                element('h3', null, '求解器'),
                choices('solverLocation', '求解位置', [
                  { value: 'local', label: '本地', hint: '在当前电脑上运行求解' },
                  { value: 'server', label: '服务端', hint: '将任务交给远程求解服务' },
                ]),
                !server && choices('localSolverType', '本地求解方式', [
                  { value: 'software', label: '软件', hint: '直接运行已安装的 LS-DYNA' },
                  { value: 'service', label: '求解服务', hint: '连接本机运行的求解服务' },
                ]),
                !service && pathField(fields.find(field => field.id === 'lsdyna')),
                service && element('div', { className: 'cae-settings-service' },
                  element('div', { className: 'cae-settings-field' },
                    element('label', { htmlFor: `cae-${urlField}` }, server ? '服务端地址' : '本地求解服务地址'),
                    element('div', { className: 'cae-settings-input-row' }, element('input', {
                      id: `cae-${urlField}`, type: 'url', required: true,
                      value: values[urlField], spellCheck: false,
                      placeholder: server ? 'https://solver.example.com' : 'http://127.0.0.1:8000',
                      onChange: event => update(urlField, event.target.value),
                    })),
                    element('p', { className: 'cae-settings-hint' }, '模型及其引用文件需能被求解服务访问，求解结果路径由服务返回。'),
                  ),
                  element('div', { className: 'cae-settings-field' },
                    element('label', { htmlFor: `cae-${tokenField}` }, '访问令牌（可选）'),
                    element('div', { className: 'cae-settings-input-row' },
                      element('input', {
                        id: `cae-${tokenField}`, type: 'password', autoComplete: 'off',
                        value: values[tokenField], placeholder: '服务未启用认证时留空',
                        onChange: event => update(tokenField, event.target.value),
                      }),
                      element('button', {
                        type: 'button',
                        onClick: () => void run(async () => {
                          setServiceCheck(null)
                          const result = await api.checkService(values)
                          setServiceCheck(result)
                          setFailed(!result.valid)
                          setMessage(result.message)
                        }),
                      }, '测试连接'),
                    ),
                    serviceCheck && element('p', { className: 'cae-settings-path-status', 'data-valid': serviceCheck.valid }, serviceCheck.message),
                  ),
                ),
              ),
              element('div', { className: 'cae-settings-group' },
                element('h3', null, '前处理与后处理'),
                ...fields.filter(field => !['lsdyna', 'workdir'].includes(field.id)).map(pathField),
              ),
              pathField(fields.find(field => field.id === 'workdir')),
              element('div', { className: 'cae-settings-actions' },
                element('button', {
                  type: 'button',
                  onClick: () => void run(async () => {
                    const result = await api.checkPaths(values)
                    setChecks(result)
                    const invalid = Object.values(result).some(check => !check.valid && !check.empty)
                    setFailed(invalid)
                    setMessage(invalid ? '部分路径不可用，请检查后修改。' : '路径检查完成。未配置的软件可以稍后填写。')
                  }),
                }, '检查路径'),
                element('button', { type: 'submit', className: 'cae-settings-primary' }, busy ? '处理中…' : '保存并重启'),
              ),
            ),
          ),
        element('p', { role: failed ? 'alert' : 'status', className: 'cae-settings-message', 'data-failed': failed }, values ? message : ''),
      )
    }

    const css = `
      .cae-simulation-settings { max-width: 760px; color: var(--dsw-alias-label-primary); }
      .cae-simulation-settings h2 { margin: 0 0 10px; font-size: 18px; font-weight: 600; }
      .cae-settings-intro, .cae-settings-note { font-size: 13px; line-height: 1.7; }
      .cae-settings-intro { color: var(--dsw-alias-label-secondary); margin: 0 0 14px; }
      .cae-settings-note { border: 1px solid var(--dsw-alias-border-l2); border-radius: 10px; padding: 12px; margin: 0 0 22px; color: var(--dsw-alias-label-secondary); }
      .cae-simulation-settings fieldset { border: 0; padding: 0; margin: 0; min-width: 0; }
      .cae-settings-group { margin-bottom: 24px; padding-bottom: 4px; border-bottom: 1px solid var(--dsw-alias-border-l2); }
      .cae-settings-group h3 { margin: 0 0 16px; font-size: 14px; font-weight: 600; }
      .cae-simulation-settings .cae-settings-choices { margin-bottom: 20px; }
      .cae-settings-choices legend { margin-bottom: 8px; font-size: 14px; font-weight: 500; }
      .cae-settings-choice-row { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
      .cae-settings-choice { display: flex; gap: 10px; align-items: flex-start; padding: 13px; border: 1px solid var(--dsw-alias-border-l2); border-radius: 8px; cursor: pointer; }
      .cae-settings-choice[data-selected=true] { border-color: #3b82f6; background: #3b82f60d; }
      .cae-settings-choice input { margin-top: 3px; accent-color: #2563eb; }
      .cae-settings-choice strong { display: block; font-size: 13px; font-weight: 500; }
      .cae-settings-choice small { display: block; margin-top: 5px; color: var(--dsw-alias-label-secondary); font-size: 12px; line-height: 1.5; }
      .cae-settings-field { margin-bottom: 22px; }
      .cae-settings-field label { display: block; margin-bottom: 8px; font-size: 14px; font-weight: 500; }
      .cae-settings-input-row { display: flex; gap: 8px; }
      .cae-settings-input-row input, .cae-settings-input-row select { flex: 1; min-width: 0; border: 1px solid var(--dsw-alias-border-l2); border-radius: 8px; background: transparent; color: inherit; padding: 9px 10px; font: 12px/1.5 monospace; }
      .cae-settings-input-row select { width: 100%; }
      .cae-settings-input-row select option { background: var(--dsw-alias-bg-layer-1, #fff); color: var(--dsw-alias-label-primary); }
      .cae-model-heading, .cae-model-toolbar, .cae-model-test-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
      .cae-model-heading { justify-content: space-between; margin-bottom: 10px; font-size: 14px; }
      .cae-model-toolbar { margin-bottom: 12px; }
      .cae-model-toolbar button, .cae-model-test-row button { padding: 5px 10px; font-size: 12px; }
      .cae-model-toolbar button[aria-pressed=true] { color: #2563eb; border-color: #2563eb; }
      .cae-model-count { margin-left: auto; font-size: 12px; color: var(--dsw-alias-label-tertiary); }
      .cae-model-search { margin-bottom: 10px; }
      .cae-model-list { display: flex; align-content: flex-start; gap: 8px; flex-wrap: wrap; max-height: 240px; overflow-y: auto; padding: 3px; margin: -3px -3px 12px; }
      .cae-simulation-settings .cae-model-chip { border-style: dashed; border-radius: 18px; padding: 6px 12px; white-space: normal; overflow-wrap: anywhere; text-align: left; font: 12px/1.6 monospace; }
      .cae-simulation-settings .cae-model-chip[aria-pressed=true] { border-style: solid; border-color: #2563eb; background: #2563eb12; color: #2563eb; }
      .cae-model-chip small { margin-left: 8px; font: 11px/1.4 sans-serif; color: var(--dsw-alias-label-tertiary); }
      .cae-model-empty { border: 1px dashed var(--dsw-alias-border-l2); border-radius: 8px; width: 100%; margin: 0; padding: 20px 12px; text-align: center; color: var(--dsw-alias-label-tertiary); font-size: 12px; }
      .cae-model-test-row { margin-bottom: 8px; }
      .cae-simulation-settings button { border: 1px solid var(--dsw-alias-border-l2); border-radius: 8px; padding: 8px 14px; background: transparent; color: inherit; font: inherit; font-size: 13px; cursor: pointer; white-space: nowrap; }
      .cae-simulation-settings button:hover { background: var(--dsw-alias-interactive-bg-hover); }
      .cae-simulation-settings :is(button, input, select):focus-visible { outline: 2px solid #3b82f6; outline-offset: 2px; }
      .cae-simulation-settings :disabled { opacity: .6; cursor: wait; }
      .cae-settings-hint, .cae-settings-path-status { font-size: 12px; line-height: 1.6; margin: 6px 0 0; color: var(--dsw-alias-label-tertiary); }
      .cae-settings-path-status[data-valid=true] { color: #16803c; }
      .cae-settings-path-status[data-valid=false], .cae-settings-message[data-failed=true] { color: #dc2626; }
      .cae-settings-actions { display: flex; justify-content: flex-end; gap: 10px; padding-top: 6px; }
      .cae-simulation-settings .cae-settings-primary { background: #2563eb; border-color: #2563eb; color: white; }
      .cae-simulation-settings .cae-settings-primary:hover { background: #1d4ed8; }
      .cae-settings-message { min-height: 22px; margin: 12px 0 0; font-size: 13px; line-height: 1.7; }
      .cae-configure-model { display: inline-flex; align-items: center; gap: 8px; padding: 5px 8px; border: none; border-radius: 6px; background: transparent; color: var(--dsw-alias-label-secondary); font: inherit; font-size: 12px; cursor: pointer; }
      .cae-configure-model:hover { background: var(--dsw-alias-interactive-bg-hover); }
      .cae-configure-model:focus-visible { outline: 2px solid #3b82f6; outline-offset: 2px; }
      @media (max-width: 520px) { .cae-settings-choice-row { grid-template-columns: 1fr; } .cae-settings-input-row { flex-wrap: wrap; } }
    `

    return {
      inject: ['slots', 'conversation'],
      apply(ctx) {
        ctx.effect(() => {
          const style = document.createElement('style')
          style.textContent = css
          document.head.appendChild(style)
          return () => style.remove()
        })
        ctx.slots.inject('settings.section', () => ctx.slots.register({
          name: 'settings.section',
          id: 'cae-simulation',
          order: 5,
          label: '仿真软件',
        }, SimulationSettings))
        ctx.slots.inject('settings.section', () => ctx.slots.register({
          name: 'settings.section',
          id: 'cae-models',
          order: 3,
          label: '模型',
        }, ModelSettings))
        ctx.slots.inject('settings.section', () => ctx.slots.register({
          name: 'settings.section',
          id: 'cae-cache',
          order: 20,
          label: '缓存',
        }, CacheSettings))

        if (window.caeModels) {
          const api = window.caeModels
          const openModelSettings = () => {
            // The shell exposes its shared store on the public slot ledger.
            const shell = ctx.slots.entries('sidebar.settings')[0]
            shell?.store?.create().actions.openSection('cae-models')
          }
          const configured = api.load().then(settings => settings.configured).catch(() => false)
          const whenConfigured = action => {
            void configured.then(ready => {
              if (ready) action()
              else openModelSettings()
            })
          }

          ctx.effect(() => api.onOpenSettings(openModelSettings))
          function ConfigureModel({ locked, sessionId }) {
            useEffect(() => {
              if (!sessionId) return
              const block = { reason: '请先选择模型并完成配置' }
              const blocks = ctx.conversation.blocks
              blocks.set(sessionId, block)
              return () => {
                if (blocks.storeFor(sessionId).getSnapshot() === block) blocks.set(sessionId, undefined)
              }
            }, [sessionId])
            return element('button', {
              type: 'button', className: 'cae-configure-model',
              disabled: locked, onClick: openModelSettings,
              'aria-label': '选择模型',
            }, '选择模型', element('span', { 'aria-hidden': true }, '⌄'))
          }
          ctx.slots.inject('conversation.input.model', () => {
            let active = true
            let dispose
            void configured.then(ready => {
              if (!active || ready) return
              dispose = ctx.slots.register({
                name: 'conversation.input.model', priority: -100,
              }, ConfigureModel)
            })
            return () => { active = false; dispose?.() }
          })
          ctx.slots.inject('conversation.hero.agentPreset', () => {
            let active = true
            let dispose
            void configured.then(ready => {
              if (!active || ready) return
              dispose = ctx.slots.register({
                name: 'conversation.hero.agentPreset', priority: -100,
              }, ({ sessionId }) => sessionId ? null : element(ConfigureModel))
            })
            return () => { active = false; dispose?.() }
          })

          ctx.inject(['uiWorkspace'], scope => {
            const navigation = scope.uiWorkspace
            const startSession = navigation.startSession
            const guardedStart = (...args) => whenConfigured(() => startSession.apply(navigation, args))
            scope.effect(() => {
              // Pointer controls and the New Session shortcut share this service method.
              navigation.startSession = guardedStart
              return () => {
                if (navigation.startSession === guardedStart) navigation.startSession = startSession
              }
            })
          })
        }
      },
    }
  },
})

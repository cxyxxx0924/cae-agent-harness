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

    function SimulationSettings() {
      const api = window.caeSimulation
      const [values, setValues] = useState(null)
      const [checks, setChecks] = useState({})
      const [busy, setBusy] = useState(false)
      const [message, setMessage] = useState('')
      const [failed, setFailed] = useState(false)

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
        setMessage('')
      }

      return element('section', { className: 'cae-simulation-settings', 'aria-labelledby': 'cae-simulation-title' },
        element('h2', { id: 'cae-simulation-title' }, '仿真软件'),
        element('p', { className: 'cae-settings-intro' }, '配置本机的仿真软件和工作目录，保存后自动重启后台服务。'),
        element('p', { className: 'cae-settings-note' }, 'Mac 上可以先测试界面和模型对话，软件路径可暂时留空；实际仿真请在安装了对应软件的 Windows 电脑上配置。'),
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
              ...fields.map(field => element('div', { key: field.id, className: 'cae-settings-field' },
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
              )),
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
      .cae-settings-field { margin-bottom: 22px; }
      .cae-settings-field label { display: block; margin-bottom: 8px; font-size: 14px; font-weight: 500; }
      .cae-settings-input-row { display: flex; gap: 8px; }
      .cae-settings-input-row input { flex: 1; min-width: 0; border: 1px solid var(--dsw-alias-border-l2); border-radius: 8px; background: transparent; color: inherit; padding: 9px 10px; font: 12px/1.5 monospace; }
      .cae-simulation-settings button { border: 1px solid var(--dsw-alias-border-l2); border-radius: 8px; padding: 8px 14px; background: transparent; color: inherit; font: inherit; font-size: 13px; cursor: pointer; white-space: nowrap; }
      .cae-simulation-settings button:hover { background: var(--dsw-alias-interactive-bg-hover); }
      .cae-simulation-settings :is(button, input):focus-visible { outline: 2px solid #3b82f6; outline-offset: 2px; }
      .cae-simulation-settings :disabled { opacity: .6; cursor: wait; }
      .cae-settings-hint, .cae-settings-path-status { font-size: 12px; line-height: 1.6; margin: 6px 0 0; color: var(--dsw-alias-label-tertiary); }
      .cae-settings-path-status[data-valid=true] { color: #16803c; }
      .cae-settings-path-status[data-valid=false], .cae-settings-message[data-failed=true] { color: #dc2626; }
      .cae-settings-actions { display: flex; justify-content: flex-end; gap: 10px; padding-top: 6px; }
      .cae-simulation-settings .cae-settings-primary { background: #2563eb; border-color: #2563eb; color: white; }
      .cae-simulation-settings .cae-settings-primary:hover { background: #1d4ed8; }
      .cae-settings-message { min-height: 22px; margin: 12px 0 0; font-size: 13px; line-height: 1.7; }
    `

    return {
      inject: ['slots'],
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
      },
    }
  },
})

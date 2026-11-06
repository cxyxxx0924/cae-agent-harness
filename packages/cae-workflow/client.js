window.__ModuleLoader__.load({
  id: '@cae/workflow',
  factory: require => {
    const { createElement: h, useEffect, useRef, useState } = require('react')
    const api = window.caeWorkflow
    const labels = { pending: '待开始', parameters: '待填写参数', ready: '待执行', blocked: '待配置软件', running: '执行中', review: '待确认', done: '已完成', completed: '已完成', error: '执行失败', interrupted: '执行中断' }
    const roles = { geometry: '导入模型', partitioned_model: '四分区模型', mesh_model: '网格模型', curtain_k: '气帘 K 文件', combined_k: '组合模型', d3plot: '求解结果', animation: '四视角动画', preview: '结果预览', verification: '校验记录', report: '分析报告' }
    const channels = new Map()

    async function refresh(sessionId) {
      if (!api || !sessionId) return
      let channel = channels.get(sessionId)
      if (!channel) { channel = { listeners: new Set() }; channels.set(sessionId, channel) }
      if (channel.loading) return channel.loading
      channel.loading = api.load(sessionId).then(view => {
        channel.view = view
        channel.listeners.forEach(listener => listener(view))
        return view
      }).catch(error => {
        channel.view = { ...channel.view, error: error.message || '读取工作流失败，请重试。' }
        channel.listeners.forEach(listener => listener(channel.view))
      }).finally(() => { channel.loading = null })
      return channel.loading
    }

    function useWorkflow(sessionId) {
      const [view, setView] = useState(() => channels.get(sessionId)?.view)
      useEffect(() => {
        setView(channels.get(sessionId)?.view)
        if (!api || !sessionId) return
        if (!channels.has(sessionId)) channels.set(sessionId, { listeners: new Set() })
        const channel = channels.get(sessionId)
        channel.listeners.add(setView)
        void refresh(sessionId)
        if (!channel.timer) channel.timer = window.setInterval(() => void refresh(sessionId), 1500)
        return () => {
          channel.listeners.delete(setView)
          if (!channel.listeners.size) { window.clearInterval(channel.timer); channel.timer = null }
        }
      }, [sessionId])
      return view
    }

    function Preview({ sessionId, artifact, onOpen }) {
      const [source, setSource] = useState('')
      useEffect(() => {
        let active = true
        setSource('')
        if (artifact && !artifact.remote) api.preview(sessionId, artifact.path).then(value => { if (active) setSource(value) }).catch(() => {})
        return () => { active = false }
      }, [sessionId, artifact?.path, artifact?.executionId])
      return source ? h('button', { type: 'button', className: 'cae-flow-preview-trigger', onClick: () => onOpen(source, roles[artifact.role] || artifact.role), 'aria-label': `放大查看${roles[artifact.role] || artifact.role}` }, h('img', { className: 'cae-flow-preview', src: source, alt: roles[artifact.role] || artifact.role })) : null
    }

    function Artifacts({ sessionId, artifacts = [] }) {
      const [error, setError] = useState('')
      const [expanded, setExpanded] = useState(null)
      useEffect(() => {
        if (!expanded) return
        const closeOnEscape = event => { if (event.key === 'Escape') setExpanded(null) }
        window.addEventListener('keydown', closeOnEscape)
        return () => window.removeEventListener('keydown', closeOnEscape)
      }, [expanded])
      return h('div', { className: 'cae-flow-artifacts' },
        ...artifacts.filter(artifact => ['preview', 'animation'].includes(artifact.role)).map(artifact => h(Preview, { key: artifact.path, sessionId, artifact, onOpen: (src, label) => setExpanded({ src, label }) })),
        ...artifacts.map(artifact => h('div', { key: artifact.role + artifact.path, className: 'cae-flow-artifact' },
          h('span', null, roles[artifact.role] || artifact.role),
          h('code', { title: artifact.path }, artifact.path),
          artifact.remote ? h('small', null, '服务端文件，请同步后查看') : h('button', { type: 'button', onClick: () => api.open(sessionId, artifact.path).catch(error => setError(error.message)) }, '打开'),
        )),
        expanded && h('div', { className: 'cae-flow-lightbox', role: 'dialog', 'aria-modal': 'true', 'aria-label': expanded.label, onClick: event => { if (event.target === event.currentTarget) setExpanded(null) } },
          h('button', { type: 'button', className: 'cae-flow-lightbox-close', onClick: () => setExpanded(null), 'aria-label': '关闭大图', title: '关闭（Esc）' }, '×'),
          h('img', { src: expanded.src, alt: expanded.label }),
        ),
        error && h('p', { role: 'alert' }, error),
      )
    }

    function defaultValues(view, stage) {
      const state = view.state
      const values = Object.fromEntries(stage.fields.map(field => [field.id, field.default ?? (field.type === 'checkbox' ? false : '')]))
      if (stage.id === 'import') values.workdir = view.workdir || ''
      if (stage.id === 'postprocess') {
        const result = state.stages.find(stage => stage.id === 'solve')?.artifacts.find(artifact => artifact.role === 'd3plot' && !artifact.remote)
        values.local_d3plot = result?.path || ''
        values.end_time = state.parameters.solve?.termination_time ?? ''
      }
      return { ...values, ...state.parameters[stage.id] }
    }

    function Parameters({ sessionId, view, stage, send, openSettings }) {
      const { state } = view
      const draftKey = `cae-workflow:${sessionId}:${state.id}:${stage.id}:${state.stages[state.current].attempts || 0}`
      const [values, setValues] = useState(() => {
        let draft = {}
        try { draft = JSON.parse(window.localStorage.getItem(draftKey) || '{}') } catch {}
        return { ...defaultValues(view, stage), ...draft, retry_confirmed: false }
      })
      const [busy, setBusy] = useState(false)
      const [error, setError] = useState('')
      const redirected = useRef(false)
      useEffect(() => {
        try { window.localStorage.setItem(draftKey, JSON.stringify(values)) } catch {}
      }, [values, draftKey])
      useEffect(() => {
        if (!redirected.current && view.configuration && (stage.id === 'solve' || (stage.id === 'import' && /\.(?:igs|iges)$/i.test(values.igs_file || '')))) {
          redirected.current = true
          openSettings(view.configuration.field)
        }
      }, [view.configuration?.field, values.igs_file, stage.id])

      function update(id, value) { setValues(previous => ({ ...previous, [id]: value })); setError('') }
      async function browse(field) {
        setBusy(true)
        try { const file = await api.browse(sessionId, field.id); if (file) update(field.id, file) }
        catch (error) { setError(error.message) }
        finally { setBusy(false) }
      }
      async function submit(event) {
        event.preventDefault()
        if (busy) return
        setBusy(true)
        setError('')
        try {
          const submitted = await api.submit(sessionId, state.revision, values)
          await refresh(sessionId)
          if (submitted.configuration) { openSettings(submitted.configuration.field); return }
          window.localStorage.removeItem(draftKey)
          await send(sessionId)
        } catch (error) { setError(error.message || '提交失败，请重试。'); void refresh(sessionId) }
        finally { setBusy(false) }
      }
      function field(item) {
        if (item.requiredWhen && values[item.requiredWhen[0]] !== item.requiredWhen[1]) return null
        const id = `cae-flow-${stage.id}-${item.id}`
        const required = item.requiredWhen ? true : item.required
        const props = { id, value: values[item.id] ?? '', required, 'aria-describedby': item.hint ? id + '-hint' : undefined, onChange: event => update(item.id, event.target.value) }
        let input
        if (item.type === 'checkbox') input = h('label', { className: 'cae-flow-check' }, h('input', { id, type: 'checkbox', checked: values[item.id] === true, required, onChange: event => update(item.id, event.target.checked) }), item.label)
        else if (item.type === 'select') input = h('select', props, h('option', { value: '', disabled: true }, '请选择'), ...item.choices.map(choice => h('option', { key: choice, value: choice }, ({ summary: '过程摘要', assessment: '法规评判', mixed: '四边形与三角形混合', quad: '四边形', tria: '三角形', displacement: '位移', stress: '应力', strain: '应变', pressure: '压力' })[choice] || choice)))
        else if (item.type === 'textarea') input = h('textarea', { ...props, rows: 3 })
        else input = h('div', { className: 'cae-flow-input' }, h('input', { ...props, type: item.type === 'number' ? 'number' : 'text', min: item.min, max: item.max, step: item.integer ? 1 : 'any', autoComplete: 'off' }), ['file', 'directory'].includes(item.type) && h('button', { type: 'button', onClick: () => void browse(item), 'aria-label': `选择${item.label}` }, '选择…'))
        return h('div', { className: 'cae-flow-field', key: item.id }, item.type !== 'checkbox' && h('label', { htmlFor: id }, item.label, required && h('span', { 'aria-hidden': true }, ' *')), input, item.hint && h('small', { id: id + '-hint' }, item.hint))
      }
      return h('form', { onSubmit: event => void submit(event) },
        h('p', { className: 'cae-flow-help' }, stage.help),
        state.error && h('p', { className: 'cae-flow-warning', role: 'alert' }, state.error),
        view.configuration && h('div', { className: 'cae-flow-warning', role: 'status' }, view.configuration.message, h('button', { type: 'button', onClick: () => openSettings(view.configuration.field) }, '打开软件设置')),
        h('fieldset', { disabled: busy },
          ...stage.fields.map(field),
          state.additionalRequest && h('div', { className: 'cae-flow-warning' }, h('p', null, state.additionalRequest), field({ id: 'additional_input', label: '补充参数或说明', type: 'textarea', required: true })),
          ['error', 'interrupted'].includes(state.status) && stage.id === 'solve' && field({ id: 'retry_confirmed', label: '已检查实际求解任务，确认可以重新提交', type: 'checkbox', required: true }),
          h('button', { className: 'cae-flow-primary', type: 'submit' }, busy ? '正在提交…' : state.status === 'ready' ? '继续执行' : stage.action),
        ),
        error && h('p', { className: 'cae-flow-error', role: 'alert' }, error),
      )
    }

    function Review({ sessionId, state }) {
      const [feedback, setFeedback] = useState('')
      const [busy, setBusy] = useState(false)
      const [error, setError] = useState('')
      async function act(adjust) {
        if (busy) return
        setBusy(true)
        setError('')
        try {
          if (adjust) await api.adjust(sessionId, state.revision, feedback)
          else await api.confirm(sessionId, state.revision)
          await refresh(sessionId)
        } catch (error) { setError(error.message) }
        finally { setBusy(false) }
      }
      return h('div', { className: 'cae-flow-review' },
        h('p', null, '校验已通过。请查看实际模型和预览，确认后进入下一阶段。'),
        h('button', { type: 'button', className: 'cae-flow-primary', disabled: busy, onClick: () => void act(false) }, '确认结果，继续下一步'),
        h('label', { htmlFor: 'cae-flow-feedback' }, '需要调整'),
        h('textarea', { id: 'cae-flow-feedback', rows: 3, value: feedback, disabled: busy, placeholder: '填写需要调整的位置、原因或参数', onChange: event => setFeedback(event.target.value) }),
        h('button', { type: 'button', disabled: busy || !feedback.trim(), onClick: () => void act(true) }, '返回参数并调整'),
        error && h('p', { role: 'alert', className: 'cae-flow-error' }, error),
      )
    }

    const css = `
      .cae-flow { height: 100%; overflow: auto; box-sizing: border-box; padding: 20px; color: var(--dsw-alias-label-primary); font-size: 13px; line-height: 1.65; overflow-wrap: anywhere; }
      .cae-flow h2 { font-size: 18px; margin: 0 0 4px; font-weight: 600; }
      .cae-flow h3 { font-size: 15px; margin: 22px 0 8px; font-weight: 600; }
      .cae-flow p { margin: 8px 0 14px; white-space: pre-wrap; }
      .cae-flow-help, .cae-flow small { color: var(--dsw-alias-label-secondary); }
      .cae-flow button, .cae-flow-entry { font: inherit; color: inherit; background: transparent; border: 1px solid var(--dsw-alias-border-l2); border-radius: 7px; padding: 6px 10px; cursor: pointer; }
      .cae-flow button:hover, .cae-flow-entry:hover { background: var(--dsw-alias-interactive-bg-hover); }
      .cae-flow button:disabled { opacity: .55; cursor: default; }
      .cae-flow :is(input, select, textarea, button):focus-visible, .cae-flow-entry:focus-visible { outline: 2px solid #3b82f6; outline-offset: 2px; }
      .cae-flow .cae-flow-primary { background: #2563eb; color: #fff; border-color: #2563eb; }
      .cae-flow-steps { list-style: none; padding: 0; margin: 18px 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(112px, 1fr)); gap: 7px; }
      .cae-flow-steps button { width: 100%; text-align: left; }
      .cae-flow-steps button[aria-current=step] { border-color: #2563eb; }
      .cae-flow-steps small { display: block; font-size: 11px; }
      .cae-flow fieldset { border: 0; padding: 0; min-width: 0; }
      .cae-flow-field { margin: 16px 0; }
      .cae-flow-field label, .cae-flow-review > label { display: block; margin-bottom: 6px; font-weight: 500; }
      .cae-flow-field small { display: block; font-size: 12px; margin-top: 5px; }
      .cae-flow :is(input:not([type=checkbox]), select, textarea) { font: inherit; border: 1px solid var(--dsw-alias-border-l2); background: transparent; color: inherit; border-radius: 7px; padding: 8px; width: 100%; min-width: 0; box-sizing: border-box; }
      .cae-flow select option { background: var(--dsw-alias-bg-layer-1, #fff); color: var(--dsw-alias-label-primary); }
      .cae-flow textarea { resize: vertical; }
      .cae-flow-input { display: flex; gap: 7px; }
      .cae-flow-input button { flex-shrink: 0; }
      .cae-flow .cae-flow-check { display: flex; align-items: flex-start; gap: 9px; font-weight: 400; }
      .cae-flow-check input { margin-top: 5px; }
      .cae-flow-warning { padding: 12px; border: 1px solid #d49730; border-radius: 8px; margin: 14px 0; }
      .cae-flow-warning button { display: block; margin-top: 9px; }
      .cae-flow-error { color: #dc2626; white-space: pre-wrap; }
      .cae-flow-artifacts { margin: 14px 0; }
      .cae-flow-artifact { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px; padding: 10px 0; border-bottom: 1px solid var(--dsw-alias-border-l2); }
      .cae-flow-artifact code { width: 100%; font-size: 11px; word-break: break-all; color: var(--dsw-alias-label-secondary); }
      .cae-flow-preview-trigger { display: block; width: 100%; border: 0 !important; padding: 0 !important; margin: 12px 0; background: transparent !important; cursor: zoom-in !important; }
      .cae-flow-preview { display: block; max-width: 100%; max-height: 420px; object-fit: contain; margin: 0 auto; border-radius: 6px; }
      .cae-flow-lightbox { position: fixed; z-index: 10000; inset: 0; display: flex; align-items: center; justify-content: center; padding: 24px; box-sizing: border-box; background: rgb(8 12 18 / 88%); }
      .cae-flow-lightbox img { display: block; max-width: min(96vw, 1800px); max-height: 92vh; object-fit: contain; }
      .cae-flow .cae-flow-lightbox-close { position: absolute; top: max(12px, env(safe-area-inset-top)); right: max(12px, env(safe-area-inset-right)); width: 42px; height: 42px; padding: 0; border: 1px solid rgb(255 255 255 / 45%); background: rgb(0 0 0 / 45%); color: #fff; font-size: 28px; line-height: 1; }
      @media (max-width: 600px) { .cae-flow-lightbox { padding: 12px; } .cae-flow-lightbox img { max-width: 100%; max-height: 88vh; } }
      .cae-flow-review > label { margin-top: 20px; }
      .cae-flow-review textarea { margin-bottom: 8px; }
      .cae-flow-traces { padding-left: 20px; font-size: 12px; color: var(--dsw-alias-label-secondary); }
      .cae-flow-traces li { padding: 6px 0; white-space: pre-wrap; }
      .cae-flow-traces time { display: block; font-size: 11px; }
      .cae-flow-dock { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; padding: 9px 12px; font-size: 12px; color: var(--dsw-alias-label-secondary); }
      .cae-flow-entry { font-size: 12px; padding: 5px 8px; white-space: nowrap; }
    `

    return {
      inject: ['slots', 'sessions', 'conversation', 'sidebarRight', 'sidebarRightTabs'],
      apply(ctx) {
        const open = () => ctx.sidebarRight.openTab('cae-workflow')
        const openSettings = field => window.dispatchEvent(new CustomEvent('cae:open-simulation-settings', { detail: { field } }))
        async function send(sessionId) {
          if (window.caeModels && !(await window.caeModels.load()).configured) {
            ctx.slots.entries('sidebar.settings')[0]?.store?.create().actions.openSection('cae-models')
            throw new Error('参数已保存。请先配置模型，返回后点击“继续执行”。')
          }
          const scoped = ctx.sessions.scope(sessionId)
          if (!scoped) throw new Error('当前对话已关闭，请重新打开后继续。')
          const conversation = scoped.get('conversation')
          if (!conversation) throw new Error('对话服务尚未就绪，请稍后继续。')
          await conversation.send('用户已在仿真工作流表单提交当前阶段参数。请先调用 cae_workflow begin，读取返回的当前 skill 和参数文件，仅执行这一个阶段。使用真实工具和产物回报 complete；缺少额外参数时调用 request_input 并等待用户填写。')
        }

        function WorkflowPanel({ sessionId }) {
          const view = useWorkflow(sessionId)
          const [selected, setSelected] = useState(null)
          const [error, setError] = useState('')
          const state = view?.state
          useEffect(() => { setSelected(null); setError('') }, [sessionId, state?.current, state?.status])
          if (!api) return h('section', { className: 'cae-flow' }, h('h2', null, '气帘仿真工作流'), h('p', null, '请在 CAE Agent 桌面应用中选择本机文件并执行工作流。'))
          if (!view) return h('p', { className: 'cae-flow', role: 'status' }, '正在读取工作流…')
          if (!state) return h('section', { className: 'cae-flow' }, h('h2', null, '气帘仿真工作流'), h('p', null, '从 IGS 几何开始，逐步完成四分区、网格、求解、后处理和报告。每个阶段开始前会提示填写本项目需要的参数。'), h('button', { type: 'button', className: 'cae-flow-primary', onClick: () => api.create(sessionId).then(() => refresh(sessionId)).catch(error => setError(error.message)) }, '新建仿真工作流'), (error || view.error) && h('p', { role: 'alert' }, error || view.error))
          const index = selected ?? state.current
          const stage = view.stages[index]
          return h('section', { className: 'cae-flow', 'aria-label': '气帘仿真工作流' },
            h('h2', null, state.parameters.import?.project_name || '气帘仿真工作流'),
            h('small', { role: 'status' }, `第 ${state.current + 1} / ${view.stages.length} 阶段 · ${labels[state.status] || state.status}`),
            h('ol', { className: 'cae-flow-steps' }, ...view.stages.map((step, i) => h('li', { key: step.id }, h('button', { type: 'button', disabled: i > state.current, 'aria-current': i === index ? 'step' : undefined, onClick: () => setSelected(i) }, `${i + 1}. ${step.title}`, h('small', null, labels[state.stages[i].status] || '待开始'))))),
            h('h3', null, stage.title),
            index === state.current && ['parameters', 'ready', 'blocked', 'error', 'interrupted'].includes(state.status) && h(Parameters, { key: `${state.id}:${stage.id}:${state.stages[index].attempts || 0}`, sessionId, view, stage, send, openSettings }),
            index === state.current && state.status === 'running' && h('div', { role: 'status', className: stage.id === 'solve' ? 'cae-flow-warning' : '' }, h('p', null, stage.id === 'solve' ? '正在执行组合求解，通常需要数小时。实际工具输出会显示在左侧对话中，结果验证通过后进入下一步。' : `${stage.title}正在执行，请查看左侧对话中的工具输出。`), h('small', null, `开始时间：${new Date(state.startedAt).toLocaleString()}`)),
            h(Artifacts, { sessionId, artifacts: state.stages[index].artifacts }),
            index === state.current && state.status === 'review' && h(Review, { key: state.executionId, sessionId, state }),
            state.status === 'completed' && h('p', { role: 'status' }, '工作流已完成，可打开报告并查看各阶段产物。'),
            view.error && h('p', { role: 'alert', className: 'cae-flow-error' }, view.error),
            h('details', null, h('summary', null, '执行记录'), h('ol', { className: 'cae-flow-traces' }, ...state.traces.slice().reverse().map((trace, i) => h('li', { key: i }, h('time', null, new Date(trace.time).toLocaleString()), trace.text)))),
          )
        }

        function WorkflowEntry({ sessionId }) {
          const view = useWorkflow(sessionId)
          return h('button', { type: 'button', className: 'cae-flow-entry', onClick: open, title: '打开当前对话的仿真工作流' }, view?.state ? `仿真 · ${labels[view.state.status] || '进行中'}` : '仿真工作流')
        }
        function WorkflowDock({ sessionId }) {
          const view = useWorkflow(sessionId)
          if (!view?.state || view.state.status === 'completed') return null
          const stage = view.stages[view.state.current]
          return h('div', { className: 'cae-flow-dock', role: 'status' }, h('span', null, `${stage.title} · ${labels[view.state.status]}`, view.state.status === 'running' && stage.id === 'solve' ? '，通常需要数小时' : ''), h('button', { type: 'button', className: 'cae-flow-entry', onClick: open }, ['parameters', 'blocked'].includes(view.state.status) ? '填写参数 / 配置' : '查看工作流'))
        }
        ctx.effect(() => { const style = document.createElement('style'); style.textContent = css; document.head.appendChild(style); return () => style.remove() })
        ctx.effect(() => ctx.sidebarRightTabs.register({ id: '@cae/workflow', kind: 'cae-workflow', keepMounted: true, title: () => '仿真工作流', guide: [{ id: 'start', order: 2, title: () => '气帘仿真工作流', description: () => '导入几何、确认参数并逐步执行仿真' }] }))
        for (const [name, component] of [['sidebar.right.pane.tab', WorkflowPanel], ['conversation.session.header.utilities', WorkflowEntry], ['conversation.input.dock', WorkflowDock]]) {
          ctx.slots.inject(name, () => ctx.slots.register({ name, ...(name === 'sidebar.right.pane.tab' ? { key: '@cae/workflow' } : { id: '@cae/workflow', order: 10 }) }, component))
        }
      },
    }
  },
})

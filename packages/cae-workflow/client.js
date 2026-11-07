window.__ModuleLoader__.load({
  id: '@cae/workflow',
  factory: require => {
    const { createElement: h, useEffect, useRef, useState } = require('react')
    const api = window.caeWorkflow
    const labels = { pending: '待开始', parameters: '待填写参数', ready: '待执行', blocked: '待配置软件', running: '执行中', review: '待确认', done: '已完成', completed: '已完成', error: '执行失败', interrupted: '执行中断' }
    const roles = { geometry: '导入模型', partitioned_model: '四分区模型', geometry_verification: '分区几何校验', mesh_model: '网格模型', curtain_k: '气帘 K 文件', combined_k: '组合模型', d3plot: '求解结果', animation: '四视角动画', preview: '结果预览', verification: '校验记录', report: '分析报告' }
    const channels = new Map()

    function channelFor(sessionId) {
      if (!channels.has(sessionId)) channels.set(sessionId, { listeners: new Set() })
      return channels.get(sessionId)
    }

    function snapshot(channel) {
      return channel?.view ? { ...channel.view, starting: Boolean(channel.starting), startError: channel.startError || '' } : undefined
    }

    function publish(channel) {
      const view = snapshot(channel)
      channel.listeners.forEach(listener => listener(view))
    }

    function settleStart(channel, error = '') {
      channel.starting?.unsubscribe?.()
      channel.starting = null
      channel.startError = error
      publish(channel)
    }

    function reconcileStart(channel) {
      const pending = channel.starting
      if (!pending?.accepted) return
      const state = channel.view?.state
      if (!state || state.revision < pending.revision) return
      if (state.id !== pending.workflowId || state.current !== pending.stage || state.status !== 'ready') settleStart(channel)
      else if (pending.finished) settleStart(channel, '对话已结束，当前阶段尚未开始。请查看左侧对话中的提示后继续。')
    }

    async function refresh(sessionId) {
      if (!api || !sessionId) return
      const channel = channelFor(sessionId)
      if (channel.loading) return channel.loading
      channel.loading = api.load(sessionId).then(view => {
        channel.view = view
        reconcileStart(channel)
        publish(channel)
        return view
      }).catch(error => {
        channel.view = { ...channel.view, error: error.message || '读取工作流失败，请重试。' }
        publish(channel)
      }).finally(() => { channel.loading = null })
      return channel.loading
    }

    function useWorkflow(sessionId) {
      const [current, setCurrent] = useState(() => ({ sessionId, view: snapshot(channels.get(sessionId)) }))
      useEffect(() => {
        const update = view => setCurrent({ sessionId, view })
        update(snapshot(channels.get(sessionId)))
        if (!api || !sessionId) return
        const channel = channelFor(sessionId)
        channel.listeners.add(update)
        void refresh(sessionId)
        if (!channel.timer) channel.timer = window.setInterval(() => void refresh(sessionId), 1500)
        return () => {
          channel.listeners.delete(update)
          if (!channel.listeners.size) { window.clearInterval(channel.timer); channel.timer = null }
        }
      }, [sessionId])
      return current.sessionId === sessionId ? current.view : snapshot(channels.get(sessionId))
    }

    function stageCard(step, position, view, selected, select) {
      const current = position === view.state.current
      const status = current && view.starting ? 'starting' : view.state.stages[position].status || 'pending'
      const label = status === 'starting' ? '正在启动' : labels[status] || status
      const done = ['done', 'completed'].includes(status)
      const active = ['running', 'starting'].includes(status)
      const attention = ['blocked', 'review', 'error', 'interrupted'].includes(status)
      const icon = done
        ? h('svg', { viewBox: '0 0 20 20', fill: 'none' }, h('path', { d: 'm5 10 3.25 3.25L15 6.5', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }))
        : attention ? '!' : active ? null : String(position + 1).padStart(2, '0')
      return h('li', { key: step.id },
        h('button', {
          type: 'button', className: 'cae-flow-step', disabled: position > view.state.current,
          'data-status': status, 'data-selected': selected,
          'aria-current': current ? 'step' : undefined,
          'aria-label': `${position + 1}. ${step.title}，${label}${selected ? '，当前查看' : ''}`,
          onClick: () => select(position),
        },
          h('span', { className: 'cae-flow-step-top', 'aria-hidden': true },
            h('span', { className: `cae-flow-step-icon${active ? ' cae-flow-step-spinner' : ''}` }, icon),
            (current || selected) && h('span', { className: 'cae-flow-step-marker' }, current ? '当前阶段' : '查看中'),
          ),
          h('span', { className: 'cae-flow-step-title' }, step.title),
          h('small', { className: 'cae-flow-step-status' }, h('span', { className: 'cae-flow-step-dot', 'aria-hidden': true }), label),
        ),
      )
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

    function useLightbox() {
      const [expanded, setExpanded] = useState(null)
      useEffect(() => {
        if (!expanded) return
        const closeOnEscape = event => { if (event.key === 'Escape') setExpanded(null) }
        window.addEventListener('keydown', closeOnEscape)
        return () => window.removeEventListener('keydown', closeOnEscape)
      }, [expanded])
      return [setExpanded, expanded && h('div', { className: 'cae-flow-lightbox', role: 'dialog', 'aria-modal': 'true', 'aria-label': expanded.label, onClick: event => { if (event.target === event.currentTarget) setExpanded(null) } },
        h('button', { type: 'button', className: 'cae-flow-lightbox-close', onClick: () => setExpanded(null), 'aria-label': '关闭大图', title: '关闭（Esc）' }, '×'),
        h('img', { src: expanded.src, alt: expanded.label }),
      )]
    }

    function Artifacts({ sessionId, artifacts = [] }) {
      const [error, setError] = useState('')
      const [setExpanded, lightbox] = useLightbox()
      return h('div', { className: 'cae-flow-artifacts' },
        ...artifacts.filter(artifact => ['preview', 'animation'].includes(artifact.role)).map(artifact => h(Preview, { key: artifact.path, sessionId, artifact, onOpen: (src, label) => setExpanded({ src, label }) })),
        ...artifacts.map(artifact => h('div', { key: artifact.role + artifact.path, className: 'cae-flow-artifact' },
          h('span', null, roles[artifact.role] || artifact.role),
          h('code', { title: artifact.path }, artifact.path),
          artifact.remote ? h('small', null, '服务端文件，请同步后查看') : h('button', { type: 'button', onClick: () => api.open(sessionId, artifact.path).catch(error => setError(error.message)) }, '打开'),
        )),
        lightbox,
        error && h('p', { role: 'alert' }, error),
      )
    }

    function outputFiles(view) {
      const files = new Map()
      for (const stage of view?.state?.stages || []) {
        const title = view.stages.find(item => item.id === stage.id)?.title || stage.id
        for (const artifact of stage.artifacts) {
          const key = `${artifact.remote ? 'remote' : 'local'}:${artifact.path}`
          let file = files.get(key)
          if (!file) {
            const name = artifact.path.split(/[\\/]/).pop() || artifact.path
            const type = /^d3plot\d*$/i.test(name) ? 'D3PLOT' : (name.match(/\.([^.]+)$/)?.[1] || 'FILE').toUpperCase()
            file = { key, name, type, path: artifact.path, remote: artifact.remote, sources: [], roles: [] }
            files.set(key, file)
          }
          if (!file.sources.some(source => source.id === stage.id)) file.sources.push({ id: stage.id, title })
          const role = roles[artifact.role] || artifact.role
          if (!file.roles.includes(role)) file.roles.push(role)
        }
      }
      return [...files.values()]
    }

    function ResultFiles({ sessionId, view }) {
      const [query, setQuery] = useState('')
      const [stageId, setStageId] = useState('all')
      const [busy, setBusy] = useState('')
      const [error, setError] = useState('')
      const [setExpanded, lightbox] = useLightbox()
      const files = outputFiles(view)
      const search = query.trim().toLowerCase()
      const filtered = files.filter(file => (stageId === 'all' || file.sources.some(source => source.id === stageId)) && [file.name, file.path, ...file.roles, ...file.sources.map(source => source.title)].join(' ').toLowerCase().includes(search))

      async function act(file, preview) {
        if (busy) return
        setBusy(`${preview ? 'preview' : 'open'}:${file.key}`)
        setError('')
        try {
          if (preview) setExpanded({ src: await api.preview(sessionId, file.path), label: file.name })
          else await api.open(sessionId, file.path)
        } catch (error) { setError(`${file.name}：${error.message || '无法读取文件，请检查文件是否仍在原路径。'}`) }
        finally { setBusy('') }
      }

      return h('div', { className: 'cae-flow-results' },
        files.length > 0 && h('div', { className: 'cae-flow-file-filters' },
          h('input', { type: 'search', value: query, placeholder: '搜索文件名、路径或用途', 'aria-label': '搜索结果文件', onChange: event => setQuery(event.target.value) }),
          h('select', { value: stageId, 'aria-label': '按阶段筛选结果文件', onChange: event => setStageId(event.target.value) },
            h('option', { value: 'all' }, '全部阶段'),
            ...view.stages.filter(stage => files.some(file => file.sources.some(source => source.id === stage.id))).map(stage => h('option', { key: stage.id, value: stage.id }, stage.title)),
          ),
        ),
        h('div', { className: 'cae-flow-file-count', role: 'status', 'aria-live': 'polite' }, search || stageId !== 'all' ? `显示 ${filtered.length} / ${files.length} 个文件` : `共 ${files.length} 个文件`, files.length > 0 && h('span', null, '随工作流自动更新')),
        !files.length ? h('div', { className: 'cae-flow-file-empty' },
          h('strong', null, '暂无结果文件'),
          h('p', null, view.state ? '各阶段产物通过验证后，会自动汇总到这里。包括模型、网格、求解结果、预览和报告。' : '当前对话还没有仿真工作流。开始工作流后，可在这里查看各阶段生成的文件。'),
        ) : !filtered.length ? h('div', { className: 'cae-flow-file-empty' },
          h('strong', null, '没有匹配的文件'),
          h('p', null, '试试其他关键词，或查看全部阶段。'),
          h('button', { type: 'button', onClick: () => { setQuery(''); setStageId('all') } }, '清除筛选'),
        ) : h('ul', { className: 'cae-flow-file-list', 'aria-label': '工作流结果文件' }, ...filtered.map(file => h('li', { key: file.key, className: 'cae-flow-file' },
          h('span', { className: 'cae-flow-file-type', 'data-type': file.type.toLowerCase(), 'aria-hidden': true }, file.type.slice(0, 6)),
          h('div', { className: 'cae-flow-file-info' },
            h('strong', { title: file.name }, file.name),
            h('span', { className: 'cae-flow-file-role' }, file.roles.join(' / ')),
            h('small', null, file.sources.map(source => source.title).join(' / ')),
            h('code', { title: file.path }, file.path),
            file.remote && h('small', { className: 'cae-flow-file-remote' }, '服务端文件，请同步到本机后查看'),
          ),
          !file.remote && h('div', { className: 'cae-flow-file-actions' },
            /\.(png|jpe?g|gif|webp)$/i.test(file.path) && h('button', { type: 'button', disabled: Boolean(busy), 'aria-label': `预览 ${file.name}`, onClick: () => void act(file, true) }, busy === `preview:${file.key}` ? '读取中…' : '预览'),
            h('button', { type: 'button', disabled: Boolean(busy), 'aria-label': `打开 ${file.name}`, onClick: () => void act(file, false) }, busy === `open:${file.key}` ? '打开中…' : '打开'),
          ),
        ))),
        error && h('p', { role: 'alert', className: 'cae-flow-error' }, error),
        lightbox,
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

    function Parameters({ sessionId, view, stage, start, running, openSettings }) {
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
      const locked = busy || view.starting || running
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
        if (locked) return
        setBusy(true)
        try { const file = await api.browse(sessionId, field.id); if (file) update(field.id, file) }
        catch (error) { setError(error.message) }
        finally { setBusy(false) }
      }
      async function submit(event) {
        event.preventDefault()
        if (locked) return
        setBusy(true)
        setError('')
        try {
          const submitted = await start(sessionId, state, values)
          if (!submitted) return
          if (submitted.configuration) { openSettings(submitted.configuration.field); return }
          window.localStorage.removeItem(draftKey)
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
        h('fieldset', { disabled: locked, 'aria-busy': locked },
          ...stage.fields.map(field),
          state.additionalRequest && h('div', { className: 'cae-flow-warning' }, h('p', null, state.additionalRequest), field({ id: 'additional_input', label: '补充参数或说明', type: 'textarea', required: true })),
          ['error', 'interrupted'].includes(state.status) && stage.id === 'solve' && field({ id: 'retry_confirmed', label: '已检查实际求解任务，确认可以重新提交', type: 'checkbox', required: true }),
          h('button', { className: 'cae-flow-primary', type: 'submit', disabled: locked }, busy ? '正在提交…' : view.starting ? '正在启动…' : running ? '对话执行中…' : state.status === 'ready' ? '继续执行' : stage.action),
        ),
        view.starting && h('p', { role: 'status', className: 'cae-flow-help' }, '执行请求已提交，正在等待当前阶段启动。请查看左侧对话。'),
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
        ...(state.stages[state.current].warnings || []).map(warning => h('div', { key: warning.name, role: 'status', className: 'cae-flow-warning' }, h('p', null, `${warning.name}（WARN）：${warning.summary}`), ...warning.detail.map((row, index) => h('p', { key: index }, `${row[0]}：${typeof row[1] === 'object' ? JSON.stringify(row[1]) : row[1]}`)))),
        h('button', { type: 'button', className: 'cae-flow-primary', disabled: busy, onClick: () => void act(false) }, '确认结果，继续下一步'),
        h('label', { htmlFor: 'cae-flow-feedback' }, '需要调整'),
        h('textarea', { id: 'cae-flow-feedback', rows: 3, value: feedback, disabled: busy, placeholder: '填写需要调整的位置、原因或参数', onChange: event => setFeedback(event.target.value) }),
        h('button', { type: 'button', disabled: busy || !feedback.trim(), onClick: () => void act(true) }, '返回参数并调整'),
        error && h('p', { role: 'alert', className: 'cae-flow-error' }, error),
      )
    }

    const css = `
      .cae-flow { --cae-flow-accent: #2563eb; --cae-flow-success: #187a4d; --cae-flow-warning: #986012; --cae-flow-danger: #c23b42; height: 100%; overflow: auto; box-sizing: border-box; padding: 20px; color: var(--dsw-alias-label-primary); font-size: 13px; line-height: 1.65; overflow-wrap: anywhere; }
      body[data-ds-dark-theme] .cae-flow { --cae-flow-accent: #7aaaff; --cae-flow-success: #66d39a; --cae-flow-warning: #f5c16c; --cae-flow-danger: #ff929a; }
      .cae-flow h2 { font-size: 18px; margin: 0 0 4px; font-weight: 600; }
      .cae-flow h3 { font-size: 15px; margin: 22px 0 8px; font-weight: 600; }
      .cae-flow p { margin: 8px 0 14px; white-space: pre-wrap; }
      .cae-flow-help, .cae-flow small { color: var(--dsw-alias-label-secondary); }
      .cae-flow button, .cae-flow-entry { font: inherit; color: var(--dsw-alias-label-primary, #263148); background: transparent; border: 1px solid var(--dsw-alias-border-l2); border-radius: 7px; padding: 6px 10px; cursor: pointer; }
      .cae-flow button:enabled:hover, .cae-flow-entry:enabled:hover { background: var(--dsw-alias-interactive-bg-hover, #2631480f); }
      .cae-flow button:enabled:active, .cae-flow-entry:enabled:active { background: var(--dsw-alias-interactive-bg-active, #2631481a); }
      .cae-flow button:disabled, .cae-flow-entry:disabled { opacity: .55; cursor: not-allowed; }
      .cae-flow :is(input, select, textarea, button):focus-visible, .cae-flow-entry:focus-visible { outline: 2px solid #3b82f6; outline-offset: 2px; }
      .cae-flow .cae-flow-primary { background: #2563eb; color: #fff; border-color: #2563eb; }
      .cae-flow .cae-flow-primary:enabled:hover { background: #1d4ed8; border-color: #1d4ed8; }
      .cae-flow .cae-flow-primary:enabled:active { background: #1e40af; border-color: #1e40af; }
      .cae-flow .cae-flow-files-entry { display: flex; align-items: center; gap: 12px; width: 100%; margin: 18px 0 0; padding: 12px; text-align: left; border-radius: 10px; background: color-mix(in srgb, var(--cae-flow-accent) 4%, transparent); }
      .cae-flow-files-entry svg { flex-shrink: 0; width: 23px; height: 23px; color: var(--cae-flow-accent); }
      .cae-flow-files-entry > span:first-of-type { flex: 1; }
      .cae-flow-files-entry strong, .cae-flow-files-entry small { display: block; }
      .cae-flow-files-entry strong { font-weight: 600; }
      .cae-flow-file-badge { padding: 1px 8px; color: var(--cae-flow-accent); background: color-mix(in srgb, var(--cae-flow-accent) 10%, transparent); border-radius: 5px; font-variant-numeric: tabular-nums; }
      .cae-flow-results-back { margin-bottom: 18px; }
      .cae-flow-file-filters { display: flex; flex-wrap: wrap; gap: 8px; margin: 20px 0 12px; }
      .cae-flow-file-filters input { flex: 1 1 180px; }
      .cae-flow .cae-flow-file-filters select { flex: 1 1 120px; width: auto; }
      .cae-flow-file-count { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 4px 12px; margin: 18px 0 10px; font-size: 12px; color: var(--dsw-alias-label-secondary); }
      .cae-flow-file-count > span { color: var(--dsw-alias-label-tertiary, #81858c); }
      .cae-flow-file-list { list-style: none; padding: 0; margin: 0; border-top: 1px solid var(--dsw-alias-border-l2); }
      .cae-flow-file { display: flex; flex-wrap: wrap; align-items: flex-start; gap: 10px; padding: 16px 0; border-bottom: 1px solid var(--dsw-alias-border-l2); }
      .cae-flow-file-type { --cae-file-tone: var(--cae-flow-accent); flex-shrink: 0; display: flex; align-items: center; justify-content: center; width: 48px; height: 44px; border: 1px solid color-mix(in srgb, var(--cae-file-tone) 20%, transparent); border-radius: 8px; background: color-mix(in srgb, var(--cae-file-tone) 6%, transparent); color: var(--cae-file-tone); font-size: 10px; font-weight: 650; letter-spacing: .2px; }
      .cae-flow-file-type:is([data-type=hm], [data-type=k], [data-type=key]) { --cae-file-tone: var(--cae-flow-success); }
      .cae-flow-file-type[data-type=d3plot] { --cae-file-tone: var(--cae-flow-warning); }
      .cae-flow-file-info { flex: 1 1 180px; min-width: 0; }
      .cae-flow-file-info > :is(strong, span, small, code) { display: block; }
      .cae-flow-file-info strong { font-size: 13px; font-weight: 600; line-height: 1.5; }
      .cae-flow-file-role { font-size: 12px; margin: 3px 0 1px; }
      .cae-flow-file-info code { font-size: 11px; color: var(--dsw-alias-label-secondary); word-break: break-all; margin-top: 5px; }
      .cae-flow-file-info .cae-flow-file-remote { color: var(--cae-flow-warning); margin-top: 6px; }
      .cae-flow-file-actions { display: flex; flex-wrap: wrap; gap: 6px; margin-left: auto; }
      .cae-flow-file-actions button { font-size: 12px; padding: 4px 9px; }
      .cae-flow-file-empty { padding: 28px 16px; margin: 10px 0; text-align: center; border: 1px dashed var(--dsw-alias-border-l2); border-radius: 10px; background: color-mix(in srgb, var(--cae-flow-accent) 2%, transparent); }
      .cae-flow-file-empty strong { font-weight: 600; }
      .cae-flow-file-empty p { color: var(--dsw-alias-label-secondary); margin: 8px 0; font-size: 12px; }
      .cae-flow-entries { display: inline-flex; flex-wrap: wrap; gap: 6px; }
      .cae-flow-steps { list-style: none; padding: 0; margin: 20px 0 24px; display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 112px), 1fr)); gap: 8px; }
      .cae-flow-steps > li { min-width: 0; }
      .cae-flow .cae-flow-step { --cae-step-tone: var(--cae-flow-accent); --cae-step-tint: 4%; --cae-step-surface: linear-gradient(145deg, color-mix(in srgb, var(--cae-step-tone) var(--cae-step-tint), transparent), transparent); position: relative; isolation: isolate; display: flex; flex-direction: column; align-items: flex-start; gap: 9px; width: 100%; height: 100%; min-height: 124px; padding: 12px; overflow: hidden; box-sizing: border-box; border-radius: 11px; border-color: color-mix(in srgb, var(--cae-step-tone) 22%, transparent); background: var(--cae-step-surface); text-align: left; transition: border-color .18s ease, background-color .18s ease, box-shadow .18s ease; }
      .cae-flow .cae-flow-step:disabled { opacity: 1; }
      .cae-flow .cae-flow-step:enabled:hover { background: var(--cae-step-surface) color-mix(in srgb, var(--cae-step-tone) 7%, transparent); border-color: color-mix(in srgb, var(--cae-step-tone) 55%, transparent); }
      .cae-flow .cae-flow-step:enabled:active { background: var(--cae-step-surface) color-mix(in srgb, var(--cae-step-tone) 12%, transparent); }
      .cae-flow .cae-flow-step[data-selected=true] { border-color: color-mix(in srgb, var(--cae-step-tone) 65%, transparent); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--cae-step-tone) 14%, transparent), 0 2px 8px color-mix(in srgb, var(--cae-step-tone) 6%, transparent); }
      .cae-flow .cae-flow-step[data-status=pending] { --cae-step-tone: var(--dsw-alias-label-tertiary, #81858c); --cae-step-tint: 3%; border-color: var(--dsw-alias-border-l2); border-style: dashed; }
      .cae-flow-step[data-status=pending] .cae-flow-step-title { color: var(--dsw-alias-label-secondary); font-weight: 500; }
      .cae-flow .cae-flow-step:is([data-status=running], [data-status=starting]) { --cae-step-tint: 12%; border-color: color-mix(in srgb, var(--cae-step-tone) 65%, transparent); }
      .cae-flow .cae-flow-step:is([data-status=done], [data-status=completed]) { --cae-step-tone: var(--cae-flow-success); --cae-step-tint: 7%; }
      .cae-flow .cae-flow-step:is([data-status=blocked], [data-status=review], [data-status=interrupted]) { --cae-step-tone: var(--cae-flow-warning); --cae-step-tint: 7%; }
      .cae-flow .cae-flow-step[data-status=error] { --cae-step-tone: var(--cae-flow-danger); --cae-step-tint: 7%; }
      .cae-flow-step-top { display: flex; align-items: center; justify-content: space-between; gap: 6px; width: 100%; min-height: 27px; }
      .cae-flow-step-icon { display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; width: 27px; height: 27px; box-sizing: border-box; border-radius: 8px; color: var(--cae-step-tone); background: color-mix(in srgb, var(--cae-step-tone) 10%, transparent); font-size: 11px; font-weight: 650; font-variant-numeric: tabular-nums; }
      .cae-flow-step-icon svg { display: block; width: 18px; height: 18px; }
      .cae-flow-step-marker { color: var(--cae-step-tone); font-size: 10px; line-height: 1.3; white-space: nowrap; }
      .cae-flow-step-title { color: var(--dsw-alias-label-primary); font-size: 13px; line-height: 1.5; font-weight: 600; }
      .cae-flow .cae-flow-step-status { display: inline-flex; align-items: center; gap: 5px; margin-top: auto; color: var(--cae-step-tone); font-size: 11px; line-height: 1.4; }
      .cae-flow-step-dot { width: 5px; height: 5px; border-radius: 50%; background: currentColor; flex-shrink: 0; }
      .cae-flow-step[data-status=pending] .cae-flow-step-dot { background: transparent; box-shadow: inset 0 0 0 1px currentColor; }
      .cae-flow-step-spinner::after { content: ''; width: 13px; height: 13px; box-sizing: border-box; border: 1.8px solid color-mix(in srgb, currentColor 24%, transparent); border-top-color: currentColor; border-radius: 50%; animation: cae-flow-spin .9s linear infinite; }
      .cae-flow-step:is([data-status=running], [data-status=starting])::after { content: ''; position: absolute; left: 0; right: 0; bottom: 0; height: 2px; background: linear-gradient(90deg, transparent, var(--cae-step-tone), transparent); animation: cae-flow-scan 2.6s ease-in-out infinite; pointer-events: none; }
      @keyframes cae-flow-spin { to { transform: rotate(360deg); } }
      @keyframes cae-flow-scan { 0% { transform: translateX(-100%); opacity: 0; } 20%, 80% { opacity: .8; } 100% { transform: translateX(100%); opacity: 0; } }
      @media (prefers-reduced-motion: reduce) { .cae-flow .cae-flow-step { transition: none; } .cae-flow-step-spinner::after, .cae-flow-step:is([data-status=running], [data-status=starting])::after { animation: none; } }
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
      .cae-flow .cae-flow-lightbox-close:enabled:hover { background: rgb(0 0 0 / 70%); border-color: #fff; }
      .cae-flow .cae-flow-lightbox-close:enabled:active { background: #000; border-color: #fff; }
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
        const openResults = () => ctx.sidebarRight.openTab('cae-results')
        const openSettings = field => window.dispatchEvent(new CustomEvent('cae:open-simulation-settings', { detail: { field } }))
        const sessionFor = sessionId => ctx.sessions.binding(sessionId)?.session

        function useSessionRunning(sessionId) {
          const session = sessionFor(sessionId)
          const [running, setRunning] = useState(() => Boolean(session?.getSnapshot().running))
          useEffect(() => {
            const update = () => setRunning(Boolean(session?.getSnapshot().running))
            update()
            return session?.subscribe(update)
          }, [session])
          return running
        }

        async function start(sessionId, state, values) {
          const channel = channelFor(sessionId)
          const session = sessionFor(sessionId)
          if (channel.starting || session?.getSnapshot().running) return null
          // Keep the launch lock beyond prompt admission, until the stage or turn settles.
          const pending = { workflowId: state.id, stage: state.current, accepted: false, sawRunning: false, finished: false }
          channel.starting = pending
          channel.startError = ''
          publish(channel)
          const observe = () => {
            const running = session?.getSnapshot().running
            if (running) pending.sawRunning = true
            else if (pending.sawRunning) { pending.finished = true; void refresh(sessionId) }
          }
          pending.unsubscribe = session?.subscribe(observe)
          try {
            const submitted = await api.submit(sessionId, state.revision, values)
            pending.revision = submitted.revision
            await refresh(sessionId)
            if (submitted.configuration) return submitted
            await send(sessionId)
            pending.accepted = true
            observe()
            reconcileStart(channel)
            void refresh(sessionId)
            return submitted
          } finally {
            if (!pending.accepted && channel.starting === pending) settleStart(channel)
          }
        }

        ctx.effect(() => () => { for (const channel of channels.values()) channel.starting?.unsubscribe?.() })

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
          const running = useSessionRunning(sessionId)
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
            h('small', { role: 'status' }, `第 ${state.current + 1} / ${view.stages.length} 阶段 · ${view.starting ? '正在启动' : labels[state.status] || state.status}`),
            h('button', { type: 'button', className: 'cae-flow-files-entry', onClick: openResults, 'aria-label': `查看结果文件，共 ${outputFiles(view).length} 个` },
              h('svg', { viewBox: '0 0 24 24', fill: 'none', 'aria-hidden': true }, h('path', { d: 'M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10H3V7Zm0 4h18', stroke: 'currentColor', strokeWidth: 1.5, strokeLinecap: 'round', strokeLinejoin: 'round' })),
              h('span', null, h('strong', null, '结果文件'), h('small', null, '查看各阶段生成的模型、求解结果和报告')),
              h('span', { className: 'cae-flow-file-badge' }, outputFiles(view).length),
              h('span', { 'aria-hidden': true }, '→'),
            ),
            h('ol', { className: 'cae-flow-steps', 'aria-label': '仿真阶段' }, ...view.stages.map((step, i) => stageCard(step, i, view, i === index, setSelected))),
            h('h3', null, stage.title),
            index === state.current && ['parameters', 'ready', 'blocked', 'error', 'interrupted'].includes(state.status) && h(Parameters, { key: `${state.id}:${stage.id}:${state.stages[index].attempts || 0}`, sessionId, view, stage, start, running, openSettings }),
            index === state.current && state.status === 'running' && h('div', { role: 'status', className: stage.id === 'solve' ? 'cae-flow-warning' : '' }, h('p', null, stage.id === 'solve' ? '正在执行组合求解，通常需要数小时。实际工具输出会显示在左侧对话中，结果验证通过后进入下一步。' : `${stage.title}正在执行，请查看左侧对话中的工具输出。`), h('small', null, `开始时间：${new Date(state.startedAt).toLocaleString()}`)),
            h(Artifacts, { sessionId, artifacts: state.stages[index].artifacts }),
            index === state.current && state.status === 'review' && h(Review, { key: state.executionId, sessionId, state }),
            state.status === 'completed' && h('p', { role: 'status' }, '工作流已完成，可打开报告并查看各阶段产物。'),
            view.error && h('p', { role: 'alert', className: 'cae-flow-error' }, view.error),
            view.startError && h('p', { role: 'alert', className: 'cae-flow-error' }, view.startError),
            h('details', null, h('summary', null, '执行记录'), h('ol', { className: 'cae-flow-traces' }, ...state.traces.slice().reverse().map((trace, i) => h('li', { key: i }, h('time', null, new Date(trace.time).toLocaleString()), trace.text)))),
          )
        }

        function ResultsPanel({ sessionId }) {
          const view = useWorkflow(sessionId)
          return h('section', { className: 'cae-flow', 'aria-label': '工作流结果文件' },
            h('button', { type: 'button', className: 'cae-flow-results-back', onClick: open }, '← 返回工作流'),
            h('h2', null, '结果文件'),
            view?.state && h('small', null, view.state.parameters.import?.project_name || '气帘仿真工作流'),
            !api ? h('p', null, '请在 CAE Agent 桌面应用中查看工作流结果文件。')
              : !view ? h('p', { role: 'status' }, '正在读取结果文件…')
                : h(ResultFiles, { key: `${sessionId}:${view.state?.id || 'empty'}`, sessionId, view }),
            view?.error && h('p', { role: 'alert', className: 'cae-flow-error' }, view.error),
          )
        }

        function WorkflowEntry({ sessionId }) {
          const view = useWorkflow(sessionId)
          return h('span', { className: 'cae-flow-entries' },
            h('button', { type: 'button', className: 'cae-flow-entry', onClick: open, title: '打开当前对话的仿真工作流' }, view?.state ? `仿真 · ${view.starting ? '正在启动' : labels[view.state.status] || '进行中'}` : '仿真工作流'),
            view?.state && h('button', { type: 'button', className: 'cae-flow-entry', onClick: openResults, title: '查看当前工作流各阶段的结果文件' }, `结果文件 · ${outputFiles(view).length}`),
          )
        }
        function WorkflowDock({ sessionId }) {
          const view = useWorkflow(sessionId)
          if (!view?.state || view.state.status === 'completed') return null
          const stage = view.stages[view.state.current]
          return h('div', { className: 'cae-flow-dock', role: 'status' }, h('span', null, `${stage.title} · ${view.starting ? '正在启动' : labels[view.state.status]}`, view.state.status === 'running' && stage.id === 'solve' ? '，通常需要数小时' : ''), h('button', { type: 'button', className: 'cae-flow-entry', onClick: open }, !view.starting && ['parameters', 'blocked'].includes(view.state.status) ? '填写参数 / 配置' : '查看工作流'))
        }
        ctx.effect(() => { const style = document.createElement('style'); style.textContent = css; document.head.appendChild(style); return () => style.remove() })
        ctx.effect(() => ctx.sidebarRightTabs.register({ id: '@cae/workflow', kind: 'cae-workflow', keepMounted: true, title: () => '仿真工作流', guide: [{ id: 'start', order: 2, title: () => '气帘仿真工作流', description: () => '导入几何、确认参数并逐步执行仿真' }] }))
        ctx.effect(() => ctx.sidebarRightTabs.register({ id: '@cae/workflow-results', kind: 'cae-results', title: () => '结果文件', guide: [{ id: 'results', order: 3, title: () => 'CAE 结果文件', description: () => '查看各阶段生成的模型、求解结果和报告' }] }))
        for (const [name, component, key = '@cae/workflow'] of [['sidebar.right.pane.tab', WorkflowPanel], ['sidebar.right.pane.tab', ResultsPanel, '@cae/workflow-results'], ['conversation.session.header.utilities', WorkflowEntry], ['conversation.input.dock', WorkflowDock]]) {
          ctx.slots.inject(name, () => ctx.slots.register({ name, ...(name === 'sidebar.right.pane.tab' ? { key } : { id: key, order: 10 }) }, component))
        }
      },
    }
  },
})

import { createRequire } from 'node:module'
import { resolve, join } from 'node:path'
import { homedir } from 'node:os'
import { pathToFileURL } from 'node:url'
import stateModule from './state.cjs'
import { executionKind, toolSucceeded } from './policy.js'

const dshRequire = createRequire(import.meta.resolve('@deepseek-ai/dsh/package.json'))
const { defineTool } = await import(pathToFileURL(dshRequire.resolve('@deepseek-ai/dsh-tools')).href)
const { WorkflowStore, STAGES } = stateModule

export const inject = ['tools']

export function softwareFromEnvironment(env = process.env) {
  return {
    hmbatch: env.CAE_HMBATCH || '', hyperview: env.CAE_HYPERVIEW || '', lsdyna: env.CAE_LSDYNA || '',
    solverLocation: env.CAE_SOLVER_LOCATION || 'local', localSolverType: env.CAE_LOCAL_SOLVER_TYPE || 'software',
    solverServerUrl: env.CAE_SOLVER_SERVICE_URL || '', solverLocalServiceUrl: env.CAE_SOLVER_SERVICE_URL || '',
  }
}

export function workflowView(state) {
  const stage = state ? STAGES[state.current] : null
  const running = state?.status === 'running'
  return {
    state: state ? {
      id: state.id, sessionId: state.sessionId, revision: state.revision,
      current: state.current, status: state.status,
      jobDirectory: state.jobDirectory ?? null, executionId: state.executionId ?? null, skillPath: state.skillPath ?? null,
      configuration: state.configuration ?? null, feedback: state.feedback ?? '', additionalRequest: state.additionalRequest ?? '',
      error: state.error ?? '', startedAt: state.startedAt ?? null,
      successfulTools: running ? [...new Set((state.toolRuns || []).filter(run => run.success).map(run => run.name))] : [],
      stages: state.stages.map(({ id, status, artifacts, warnings }) => ({ id, status, artifacts, warnings: warnings || [] })),
      parameterFile: running ? join(state.jobDirectory, `${stage.id}.parameters.json`) : null,
      caseFile: running && ['mesh', 'solve'].includes(stage.id) ? join(state.jobDirectory, `${stage.id}.case.json`) : null,
      gateFile: running && stage.id === 'mesh' ? join(state.jobDirectory, 'mesh.gate.json') : null,
      recoveryFile: running && stage.id === 'mesh' ? join(state.jobDirectory, 'mesh.recovery.json') : null,
    } : null,
    stage: stage ? { id: stage.id, title: stage.title, instructions: stage.instructions, outputs: stage.outputs, review: Boolean(stage.review) } : null,
    instruction: '用户只能在应用工作流表单提交参数和确认结果。不得代用户提交、猜测样例参数或直接改状态文件。每次只执行当前阶段；运行时从 parameterFile/caseFile/gateFile 按需读取完整参数，不要读取整个工作流状态或重复加载其它阶段。网格阶段从已确认的分区模型生成案例配置，无需用户上传 case.json；如需检查预览，从之前阶段 artifacts 中读取真实预览路径。不确定的项目参数调用 request_input 暂停并说明需要填写什么。',
  }
}

export function apply(ctx) {
  const store = new WorkflowStore(process.env.CAE_WORKFLOW_DIR || join(homedir(), '.cae-agent', 'workflows'))
  const root = resolve(process.env.CAE_PROJECT_ROOT || process.cwd())
  store.interruptRunning()
  ctx.tools.register(defineTool({
    name: 'cae_workflow',
    description: 'CAE 气帘工作流：create 创建并提示用户填表；status 查看当前阶段；begin 在用户提交参数后取得执行标识、skill 和参数；complete 校验实际产物；request_input 暂停等待补充项目参数；fail 记录失败。用户的确认仅能在界面操作。',
    parameters: {
      action: { type: 'string', enum: ['create', 'status', 'begin', 'complete', 'request_input', 'fail'], required: true },
      execution_id: { type: 'string', description: 'begin 返回的当前执行标识。' },
      message: { type: 'string', description: '失败原因或需要用户补充的具体参数。' },
      artifacts: { type: 'array', items: { type: 'object', additionalProperties: false, properties: { role: { type: 'string', required: true }, path: { type: 'string', required: true }, remote: { type: 'boolean' } } }, description: '真实产物完整路径列表。门禁 verification 格式见编排 skill。' },
    },
    output: { schema: { type: 'object', additionalProperties: true }, render: (_args, value) => [{ type: 'text', text: JSON.stringify(value) }] },
    async execute(args, exec) {
      const sessionId = exec.agent?.id
      if (!sessionId) throw new Error('CAE 工作流必须绑定当前对话。')
      let state
      if (args.action === 'create') state = store.create(sessionId)
      else if (args.action === 'status') state = store.load(sessionId)
      else if (args.action === 'begin') state = store.begin(sessionId, softwareFromEnvironment(), root)
      else if (args.action === 'complete') state = store.complete(sessionId, args.execution_id, args.artifacts)
      else if (args.action === 'request_input') state = store.requestInput(sessionId, args.execution_id, args.message)
      else state = store.fail(sessionId, args.execution_id, args.message || '执行失败，请查看对话中的实际工具日志。')
      if (!state || !['ready', 'running'].includes(state.status)) exec.concludeTurn()
      return workflowView(state)
    },
  }))

  ctx.on('tools/pre-execute', async (exec, next) => {
    if (!exec.agent || exec.name === 'cae_workflow') return next()
    const kind = executionKind(exec.name, exec.arguments)
    if (!kind) return next()
    let state = store.load(exec.agent.id)
    if (!state && kind === 'cae') state = store.create(exec.agent.id)
    if (!state) return next()
    if (state.status !== 'running') return { kind: 'deny', reason: '当前 CAE 阶段正在等待用户填写参数、配置软件或确认结果。请调用 cae_workflow status，提示用户打开“仿真工作流”；只有表单提交后才能 begin。可以继续读取文档和查看文件。' }
    if (exec.name === 'mcp__cae__hypermesh_partition_airbag') return { kind: 'deny', reason: '该工具为旧三组件占位实现。请按当前分区 skill 执行 BELT/CAVITY/SEAM/TETHER 四分区。' }
    if (exec.name === 'mcp__cae__hypermesh_generate_mesh') return { kind: 'deny', reason: '请使用 docs 网格 skill 的当前案例配置和完整四门禁链。通用网格工具不支持该链路。' }
    if (exec.name === 'mcp__cae__generate_ppt_report' && (state.parameters.report?.template_pptx || state.parameters.report?.report_mode === 'assessment')) return { kind: 'deny', reason: '通用报告工具只支持无客户模板的过程摘要。请按评判与报告 skill 保留用户模板并生成完整证据报告。' }
    if (/lsdyna_solve|run_lsdyna_solver/.test(exec.name) && STAGES[state.current].id !== 'solve') return { kind: 'deny', reason: '尚未到达求解阶段。请先完成当前阶段并等待用户确认。' }
    if (/run_lsdyna_solver/.test(exec.name)) return { kind: 'deny', reason: '请使用 mcp__cae__lsdyna_solve，按用户设置选择求解后端。' }
    return next()
  })

  ctx.on('tools/execute', async (exec, next) => {
    const state = exec.agent && store.load(exec.agent.id)
    const tracked = state?.status === 'running' && executionKind(exec.name, exec.arguments)
    const result = await next()
    if (tracked) {
      const success = toolSucceeded(result)
      store.recordTool(exec.agent.id, state.executionId, exec.name, success)
      if (exec.signal.aborted) {
        const current = store.load(exec.agent.id)
        if (current?.status === 'running' && current.executionId === state.executionId) store.fail(exec.agent.id, state.executionId, '执行已停止。求解可能仍在服务端运行；请先检查实际任务状态，避免重复提交。', 'interrupted')
      }
    }
    return result
  })

  ctx.on('agent/status', ({ agent, status }) => {
    if (status !== 'idle') return
    const state = store.load(agent.id)
    if (state?.status === 'running') store.fail(agent.id, state.executionId, '对话执行已结束，但当前阶段尚未提交完整产物。请先检查本机或服务端任务和日志，确认后再继续，避免重复提交。', 'interrupted')
  })
}

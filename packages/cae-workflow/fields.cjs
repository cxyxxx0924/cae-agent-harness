const SKILLS = {
  partition: 'docs/气帘iges分区skill',
  mesh: 'docs/气帘自动网格划分_20261101(1)/气帘自动网格划分',
  solve: 'docs/气帘计算求解skill_20261102(1)/气帘计算求解skill',
  report: 'docs/气帘评判及报告skill_20261103(1)/气帘评判及报告skill',
}

const field = (id, label, type, options = {}) => ({ id, label, type, required: true, ...options })
const number = (id, label, options = {}) => field(id, label, 'number', options)
const file = (id, label, options = {}) => field(id, label, 'file', options)
const choice = (id, label, choices, options = {}) => field(id, label, 'select', { choices, ...options })

const STAGES = [
  {
    id: 'import', title: '上传 IGS', action: '导入几何', skill: SKILLS.partition,
    help: '选择当前项目的几何和工作目录。输入文件保留原样，所有产物写入独立的工作流目录。',
    fields: [
      field('project_name', '项目名称', 'text'),
      file('igs_file', '气帘 IGS / IGES 文件', { extensions: ['igs', 'iges'] }),
      field('workdir', '仿真工作目录', 'directory'),
    ],
    outputs: ['geometry'],
    instructions: '读取分区 skill。使用 t00_import_iges.tcl 导入原始 IGS，显式设置 IGES、WORKDIR、HMBATCH 和 PY，使用配置的软件路径和可用的 Python 环境，禁止回退到脚本里的个人电脑路径。交付 curves.hm 和几何预览图。',
  },
  {
    id: 'partition', title: 'AI 分区', action: '开始四分区', skill: SKILLS.partition, review: true,
    help: '识别布带 BELT、气腔 CAVITY、缝线 SEAM、拉带 TETHER。完成后展示分区图，等待确认。',
    fields: [field('notes', '几何特征或分区要求', 'textarea', { required: false })],
    outputs: ['partitioned_model', 'preview', 'verification', 'geometry_verification'],
    instructions: '使用 v2 的采样、auto_partition2.py、p06_export_class_lists.py、t07_make_comps.tcl、t08_verify_partitioned.tcl 链路，复用已导入的 curves.hm。独立回读必须 VERIFY_FAIL=0；t08 同时输出 out/partition_geometry.json，试建布带外轮廓和气腔面、检查面边界闭环以及裁切面积守恒，geometry_verification 必须 PASS。开口诊断保留线号和坐标，不能只凭条数交付或擅自加大容差。四分区渲染必须来自真实模型。不能调用旧的三组件占位工具。',
  },
  {
    id: 'mesh', title: '网格', action: '生成网格', skill: SKILLS.mesh, review: true,
    help: '填写网格尺寸和单元类型即可，无需上传 case.json。执行时会根据已确认的分区模型生成本项目配置；无法从模型或已验证文件确认的项目参数会在执行前另行询问。',
    fields: [
      number('element_size', '目标网格尺寸（mm）', { min: 0.01, max: 100, default: 5 }),
      choice('element_type', '单元类型', ['mixed', 'quad', 'tria'], { default: 'mixed' }),
      file('reference_mesh_k', '本项目已认可的参考网格 K 文件（可选）', { extensions: ['k', 'key'], required: false, hint: '用于生成分区覆盖门禁基线。没有合适的本项目参考网格时可留空，执行前会询问如何建立并确认基线。' }),
      field('notes', '网格及连接要求', 'textarea', { required: false }),
    ],
    outputs: ['mesh_model', 'curtain_k', 'preview', 'verification'],
    instructions: '先读 references/00_RUNBOOK_接新气帘.md、04_pitfalls.md、16_generic_pipeline.md 和 cases/README.md，并读取 mesh.recovery.json。mode=verify_existing 时先用 scripts/gate/readback_mesh.tcl 独立回读现有 HM、verify_mesh_readback.py 对比现有 K，重跑四道门禁后直接 complete，不要重划或刷新产物时间戳；参数或分区变化、用户要求调整或实际验证失败才返工。新建网格前运行分区 t08 的建面与裁切面积预检。根据当前 partitioned.hm 调查组件 ID、平面/厚度方向及实际分区；在 jobDirectory 内生成 mesh.case.json 和 mesh.gate.json，再调用现有脚本。不要求上传 case.json。element_size 写入 mesh.size，单元类型写入 mesh.bl_etype。不要复制 cab1/cab2 的坐标、分层、部件清单、组装参数或门禁基线；逐项核对技能脚本的实际支持和硬编码。无法从当前模型、已验证文件或脚本约束可靠确定的项目参数，用 request_input 说明字段、单位和依据并等待补充，不得猜测或略过门禁。目标 K 固定为 out/curtain_airbag.k；运行严格 K、auto_gate、质量和分区覆盖四道门禁。auto_gate 必须包含五项原始结果且无 FAIL；仅允许短边以及有 fabric 覆盖且真缺口为零的局部特征/跨 PID WARN，保留原始报告并交用户确认；其它 WARN、缺件或失败必须停止。',
  },
  {
    id: 'solve', title: '求解', action: '提交组合求解', skill: SKILLS.solve,
    help: '求解通常需要数小时，耗时取决于模型规模、网格密度和计算资源。请填写当前模型的装配与计算参数。',
    fields: [
      file('body_k', '车身 K 文件', { extensions: ['k', 'key'] }),
      file('reference_deck', '参考主控文件', { extensions: ['k', 'key'] }),
      file('material_k', '参考材料文件', { extensions: ['k', 'key'] }),
      number('placement_dy', '气帘装配 Y 平移（mm）', { hint: '按当前气帘与参考模型的顶部距离差填写。' }),
      number('placement_dz', '气帘装配 Z 平移（mm）', { hint: '按当前模型的坐标对齐结果填写。' }),
      number('tether_count', '当前模型拉带数量', { min: 1, max: 1000, integer: true }),
      number('termination_time', '正式计算终止时间（ms）', { min: 0.01, max: 100000 }),
      number('probe_time', '探针计算时长（ms）', { min: 0.01, max: 100, default: 2 }),
      number('ncpu', 'CPU 核数', { min: 1, max: 64, integer: true, default: 4 }),
      field('memory', '求解器内存', 'text', { default: '2000m', hint: '例如 2000m 或 4g；根据计算资源确认。' }),
      field('service_paths_confirmed', '已确认模型及 INCLUDE 文件可被所选求解服务访问', 'checkbox', { required: false }),
      field('hours_confirmed', '已知求解通常需要数小时，确认提交', 'checkbox'),
    ],
    outputs: ['combined_k', 'd3plot', 'verification'],
    instructions: '读取求解 skill 及 09_fresh_deck_build.md、10_full_parity_damping.md。使用 solve.case.json 当前参数，参考模型材料、载荷和控制卡保持不动；装配前做 ID 审计，跑 parity_audit 和 damper_mass_gate，再进行探针和正式求解。统一调用 mcp__cae__lsdyna_solve，显式传 ncpu、memory。正式提交前提示通常数小时。服务模式不要绕过配置运行本地求解器；只按真实工具状态汇报，不编造百分比。验证正常终止、d3plot 和健康门禁后才能完成本阶段。',
  },
  {
    id: 'postprocess', title: '后处理', action: '开始 HyperView 后处理', skill: SKILLS.report, review: true,
    help: '根据真实结果选择时刻和画面范围。服务端结果需先映射到本机可读取的位置。',
    fields: [
      file('local_d3plot', '本机可访问的 d3plot', { hint: '服务模式请填写已同步或共享的结果路径；本地结果会自动带入。' }),
      number('start_time', '动画开始时刻（ms）', { min: 0, default: 0 }),
      number('end_time', '动画结束时刻（ms）', { min: 0.01 }),
      number('frames', '动画采样帧数', { min: 2, max: 1000, integer: true, default: 21 }),
      number('fps', '动画帧率', { min: 1, max: 60, integer: true, default: 10 }),
      choice('result_type', '云图类型', ['displacement', 'stress', 'strain', 'pressure'], { default: 'displacement' }),
    ],
    outputs: ['animation', 'preview', 'verification'],
    instructions: '按 references/hyperworks_autostart.md 使用 MCP 检查 bridge，必要时启动并轮询在线；按 hyperview_postprocess.md 的真实接口传当前时刻、帧数、帧率和云图类型。生成前后左右四视角动画与末态图，逐张 MD5 检查视角有效；未验证通过不能交付。',
  },
  {
    id: 'report', title: '报告', action: '生成分析报告', skill: SKILLS.report,
    help: '可生成过程摘要，或提供法规评价需要的测点和坐标证据。缺少动态保护证据时必须写“证据不足”。',
    fields: [
      field('title', '报告标题', 'text', { default: '气帘仿真分析报告' }),
      field('analyst', '分析人员', 'text'),
      choice('report_mode', '报告内容', ['summary', 'assessment'], { default: 'summary' }),
      file('template_pptx', '客户报告模板（可选）', { extensions: ['pptx'], required: false }),
      file('head_points', '头部重心 / 落点坐标 JSON', { extensions: ['json'], requiredWhen: ['report_mode', 'assessment'] }),
      field('coordinate_system', '测点与模型的坐标系及对齐依据', 'textarea', { requiredWhen: ['report_mode', 'assessment'] }),
      number('measurement_time', '厚度评判时刻（ms）', { min: 0, requiredWhen: ['report_mode', 'assessment'] }),
      number('early_time', '展开过程对照时刻（ms）', { min: 0, requiredWhen: ['report_mode', 'assessment'] }),
      number('detonation_time', '起爆时刻（ms）', { min: 0, requiredWhen: ['report_mode', 'assessment'] }),
      number('cog5_x', '5% 头部重心 X（mm）', { requiredWhen: ['report_mode', 'assessment'] }),
      number('cog5_z', '5% 头部重心 Z（mm）', { requiredWhen: ['report_mode', 'assessment'] }),
      number('cog95_z', '95% 头部重心 Z（mm）', { requiredWhen: ['report_mode', 'assessment'], hint: '用于确定 G.3 评估区，必须与当前模型坐标一致。' }),
      number('coordinate_dx', '已验证的坐标 X 平移（mm）', { requiredWhen: ['report_mode', 'assessment'] }),
      number('coordinate_dz', '已验证的坐标 Z 平移（mm）', { requiredWhen: ['report_mode', 'assessment'] }),
      file('dynamic_evidence', '动态保护证据文件（可选）', { required: false, hint: '假人模型、接触力或加速度等证据。缺少时动态保护结论为 INDETERMINATE。' }),
      field('inflator_evidence', '真实充气机曲线的来源与验证说明（可选）', 'textarea', { required: false }),
    ],
    outputs: ['report'],
    instructions: '按 report_mode 汇总已验证的实际产物。summary 只生成过程摘要，不作法规合格判断。assessment 必须先确认头部点与模型坐标一致，再用本次 measurement_time/early_time/detonation_time 显式传 --t-main/--t-early/--tdet，用 coordinate_dx/dz 传 --dx/--dz，用 cog5_x/z/cog95_z 确定 G.3 区域，执行 g14_mesh_check.py、g14_thickness.py；不得抄样例头部坐标、时间、位移。没有接触力/加速度或真实充气机证据的判据只允许 INDETERMINATE。沿用用户模板主题；未提供模板时明确使用通用摘要。将当前参数、证据来源和缺失项写入报告。',
  },
]

module.exports = { STAGES, SKILLS }

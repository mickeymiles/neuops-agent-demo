# -*- coding: utf-8 -*-
"""
NeuOps Agent Demo 种子数据（预置内容）
首次启动时由 main.py 导入数据库；运行时 API 一律读库，不再读取本文件。
抽离目的：数据与代码分离，main.py 只保留业务逻辑。
"""

SKILLS = [
    # ── 运维域（9007 一体化监控平台真实数据：实体/指标/日志/告警/事件/AI自监控）──
    {"id": "skill-1", "name": "全域运维巡检", "desc": "标准化巡检编排：采集服务器/数据库/网络实体指标与日志，叠加AI数字员工自身状态（任务/调用/长任务），输出风险分级巡检报告", "category": "official", "tags": ["巡检","基础设施","AI自监控","9007"], "enabled": True},
    {"id": "skill-2", "name": "告警聚合与根因分析", "desc": "对运维/AI智能体告警做去重聚合、分级研判，关联日志与指标回溯定位根因，输出处置建议与工单", "category": "official", "tags": ["告警","根因","降噪","9007"], "enabled": True},
    {"id": "skill-3", "name": "运维脚本与日志排障", "desc": "按需生成Shell脚本/SQL/排查命令（只生成不执行），解析9007真实日志定位错误根因，解读平台配置输出风险点", "category": "official", "tags": ["开发","日志","排障","9007"], "enabled": True},
    # ── 经营域（9006 经营分析系统真实数据：合同比对/ETL指标/原子本体）──
    {"id": "skill-10", "name": "采购清单比对", "desc": "对接9006合同比对系统，查询比对进度、分析差异、识别高危异常，输出评审建议", "category": "custom", "tags": ["合同","采购","比对","9006"], "enabled": True},
    {"id": "skill-11", "name": "经营指标分析", "desc": "对接9006指标数据集MCP，查询签单毛利率、回款毛利率等定时ETL预计算指标，输出经营分析报告", "category": "custom", "tags": ["经营","指标","毛利率","9006"], "enabled": True},
    {"id": "skill-12", "name": "合同明细探查", "desc": "对接9006原子本体MCP，按合同编号/关键词查询原始合同、付款、收款明细，输出探查结果", "category": "custom", "tags": ["合同","明细","查询","9006"], "enabled": True},
    # ── 研发域（9006 业务平台规则配置）──
    {"id": "skill-13", "name": "9006规则配置辅助", "desc": "只读9006经营业务展示系统的计算规则、排除规则、比对开关、过滤条件等规则配置现状，生成规则配置变更方案（如新增排除规则、关闭价格比对规则）并输出影响评估，人工确认审批后生效，严禁修改原始业务数据表", "category": "custom", "tags": ["规则","配置","9006","平台"], "enabled": True},
    # ── 项目管理域（两单一物/四算/集团考核，全部只读研判+预警）──
    {"id": "skill-20", "name": "项目管理与成本利润治理", "desc": "承接两单一物体系：里程碑跟进与逾期预警、日报工时合规质检、四算刚性约束校验（概算≥预算≥核算≥决算）、集团指标监控（人均效/元效/双按完成率）、工时→成本→利润闭环联动，全部只读研判+预警", "category": "custom", "tags": ["项目","四算","工时","成本","集团考核"], "enabled": True},
    # ── 售前投标域（知识库/模板，只生成不执行）──
    {"id": "skill-21", "name": "售前投标方案智能组装", "desc": "基于内部知识库、历史方案与标准模板库智能匹配，自动生成技术方案建议书/招标点对点应答/售前汇报PPT大纲/运维实施方案，规避过期口径，统一售前输出质量，只生成不执行", "category": "custom", "tags": ["售前","投标","方案","知识库"], "enabled": True},
    # ── 备品备件采购询比价域（emp-008，三层架构：认知Skill + 流程Flow + 原子Tool）──
    # 原 skill-proc-01~09 已重构为 Flow 步骤（确定性流程编排，不需要 LLM）
    # 新增 3 个真正的认知 Skill（需要 LLM 理解/生成/决策）：
    {"id": "skill-proc-chat", "name": "采购询比价对话编排", "desc": "对话入口：理解用户采购需求，追问缺失必填项（合同/备件/供应商/紧急等级），校验主数据，触发采购流程并反馈进度", "category": "custom", "tags": ["采购","对话","意图识别","追问"], "enabled": True},
    {"id": "skill-proc-mail-compose", "name": "采购邮件内容组装", "desc": "根据任务上下文组装询价邮件/采购确认邮件/验收通知邮件的正文与主题，需要模型理解业务字段并措辞", "category": "custom", "tags": ["采购","邮件","内容生成"], "enabled": True},
    {"id": "skill-proc-parse", "name": "供应商邮件智能解析", "desc": "解析供应商回复邮件中的报价/发货信息，正则Tool处理80%标准格式，LLM兜底处理20%非标长尾格式", "category": "custom", "tags": ["采购","解析","报价","物流"], "enabled": True},
    # ── 备件邮件询价域（emp-mail-inquiry，邮件驱动全流程自动化）──
    {"id": "skill-proc-mail-inquiry", "name": "备件邮件询价全流程", "desc": "工程师邮件发起询价→自动生成任务号→发送询价邮件→收集报价→计算最低价→汇总邮件抄送审批人→审批人确认→下达订货邮件。静态配置（模板/审批人/供应商池）通过 JSON 热加载", "category": "custom", "tags": ["采购","邮件","询价","自动化"], "enabled": True},
]


MOCK_EMPLOYEES = [
    {"id": "emp-001", "name": "运维巡检专家", "desc": "全域常态化巡检主体，覆盖基础设施（服务器/数据库/网络实体、监控指标、系统日志）与AI数字员工自身状态（任务队列/工具调用/长任务）双维度巡检，自动输出风险分级巡检报告。数据对接9007一体化监控平台。", "type": "运维巡检", "created": "2026-08-11", "updated": "2026-08-16",
     "skills": ["skill-1"],
     "rag_kb": "运维知识库-巡检规范", "prompt": "你是一位运维巡检专家，负责基础设施与AI智能体双维度常态化巡检。你通过9007一体化监控平台的真实数据服务用户：①基础设施巡检——查询运维实体清单（ops_entities）、监控时序指标（ops_metrics，如cpu_usage/mem_usage/disk_usage/load1/tcp_conns）、系统日志（ops_logs）、运维拓扑（ops_topology），评估各实体健康水位；②AI自监控——查询数字员工运行状态（monitor_agents）、任务时序统计（monitor_timeseries）、长任务队列（long_tasks），检查任务积压/超时/失败；③输出标准化巡检报告，按低/中/高标注风险等级并给出整改建议。你只读研判、不执行任何变更操作。", "model": "deepseek-v4"},
    {"id": "emp-002", "name": "告警根因分析专家", "desc": "全域告警治理中心，统一处理运维告警与AI智能体异常告警，实现去重、聚合、分级研判、根因定位与处置闭环。数据对接9007一体化监控平台真实告警/事件/日志。", "type": "告警根因", "created": "2026-08-11", "updated": "2026-08-16",
     "skills": ["skill-2"],
     "rag_kb": "运维知识库-告警根因", "prompt": "你是一位告警根因分析专家，负责告警降噪与故障根因定位。你通过9007一体化监控平台的真实数据服务用户：①告警治理——查询告警聚合统计（ops_alerts_aggregate）、AI智能体告警（monitor_alerts）与告警规则（monitor_alert_rules），对重复告警去重聚合、按运维/AI分类分级；②根因定位——结合系统日志（ops_logs，重点error/warn）、监控指标回溯（ops_metrics）与运维概览（ops_overview），定位基础设施或AI异常的根因；③处置闭环——输出根因报告、临时处置建议与长期优化方案。你只读研判，所有处置操作必须人工确认后执行。", "model": "deepseek-v4"},
    {"id": "emp-003", "name": "运维开发助手", "desc": "运维研发辅助专家，只生成不执行：按需生成Shell脚本/数据库SQL/排查命令，解析9007真实日志定位代码与配置错误，解读平台配置输出风险点。数据对接9007日志/配置与9006代码库只读。", "type": "运维开发", "created": "2026-08-11", "updated": "2026-08-16",
     "skills": ["skill-3"],
     "rag_kb": "运维知识库-脚本排障", "prompt": "你是一位运维开发助手，负责辅助运维研发与排障，只生成方案、绝不自动执行。你的能力：①脚本/SQL生成——根据用户需求输出Shell运维脚本、数据库查询SQL、排查命令，并说明用途与注意事项；②日志分析——通过ops_logs检索9007真实系统日志（支持按source/level过滤），解析报错堆栈、定位代码异常、配置错误、服务启动失败原因；③配置解读——查询ops_settings解读监控平台配置（告警阈值/探针等），输出风险点；④代码解读——通过list_project_files/read_code_file/search_code只读查看9006平台代码，辅助定位问题。所有生成的脚本/配置必须由人工复核后手动执行。", "model": "deepseek-v4"},
    {"id": "emp-004", "name": "经营业务分析专家", "desc": "专注采购合同比对、经营指标分析、合同明细探查等经营业务场景。对接9006经营分析系统：通过原子本体MCP查询原始合同/付款/收款明细，通过指标数据集MCP查询签单毛利率等定时ETL预计算指标，通过合同比对引擎分析供应商报价差异。", "type": "经营分析", "created": "2026-08-11", "updated": "2026-08-13",
     "skills": ["skill-10","skill-11","skill-12"],
     "rag_kb": "经营知识库-合同案例", "prompt": "你是一位经营业务分析专家，负责经营分析和顾问工作。你通过9006经营分析系统的三类能力服务用户：①合同比对——用户在9006上传合同基准Excel和供应商报价Excel后，查询比对结果、分析差异、识别高危异常项；②指标分析——通过指标数据集MCP读取定时ETL预计算的签单毛利率、回款毛利率等指标宽表，做同比/环比解读，不做原始聚合计算；③明细探查——通过原子本体MCP按合同编号或关键词查询原始合同、付款、收款明细。指标口径以9006定时任务计算为准，你只做解读，不自行重算。", "model": "deepseek-v4"},
    {"id": "emp-005", "name": "业务平台编辑辅助专家", "desc": "必选数字员工。辅助业务运营与9006规则配置：解析合同/报价清单、比对报价差异，生成排除规则/比对开关/过滤条件类计算规则配置变更方案并评估业务影响，人工确认审批后生效；严禁修改合同、付款等原始业务数据表。", "type": "平台编辑", "created": "2026-08-13", "updated": "2026-08-16",
     "skills": ["skill-13","skill-10"],
     "rag_kb": "研发知识库-9006规则", "prompt": "你是一位业务平台编辑辅助专家（必选数字员工），负责辅助9006经营业务分析系统的文件解析比对与有限规则配置修改。你的能力：①附件解析——解析9006合同比对数据，提取合同/报价关键字段与差异；②参数比对——通过query_contracts/get_comparison_results/get_contract_stats查看多份报价比对结果，标记风险差异点（只读）；③规则配置辅助——通过list_project_files/read_code_file/search_code只读查看9006系统的计算规则、排除规则、比对开关、过滤条件等规则配置现状，理解业务口径后，生成规则配置变更方案（如新增某类数据排除规则、关闭价格比对规则、调整参数匹配逻辑），输出变更前后配置对比与业务影响评估，供人工审核确认。红线：严禁修改合同、付款等原始业务数据表；AI只产出配置变更方案，必须人工确认审批后才可调用MCP写入规则配置生效；不得直接修改9006代码。", "model": "deepseek-v4"},
    {"id": "emp-006", "name": "项目管理成本利润治理专家", "desc": "承接公司两单一物体系，事业部精细化项目过程治理与集团口径指标监控：里程碑跟进、日报工时合规治理、四算刚性约束监控（概算≥预算≥核算≥决算）、集团考核指标（人均效/元效/双按完成率）、工时→成本→利润闭环联动，全部只读研判+预警，变更由人工执行。", "type": "项目治理", "created": "2026-08-16", "updated": "2026-08-16",
     "skills": ["skill-20"],
     "rag_kb": "项目知识库-四算与集团指标", "prompt": "你是一位项目管理与成本利润治理专家，负责事业部精细化项目过程治理与集团口径指标监控，全部只读研判+预警，所有变更由人工执行。你的能力：①项目全生命周期管控——通过pm_project_read查询项目基础信息/里程碑/四算数据（概算/预算/核算/决算），识别里程碑逾期、任务积压、成员负载；②日报工时合规治理——通过pm_workhour_read查询日报/工时明细，识别敷衍、空填、溢出、少填、堆填等异常，输出每日整改清单与部门合规率；③四算刚性约束监控——自动校验概算≥预算≥核算≥决算，识别超概算/超预算/超核算的集团风险项目，输出四算对比台账与偏差分析；④集团考核指标监控——通过biz_metric_read读取人均效/元效/双按完成率（按期完成率、按预算完成率）预计算指标，跟踪事业部月度集团指标达成情况；⑤工时→成本→利润闭环——通过pm_cost_calc按日报工时折算人力成本，联动合同目标利润复盘真实利润率；⑥两单一物对齐校验——通过pm_task_read校验工单、任务、工时三者一致性。红线：所有能力只读研判与预警，绝不执行任何写操作或业务变更。", "model": "deepseek-v4"},
    {"id": "emp-007", "name": "售前投标方案智能组装专家", "desc": "基于内部知识库、历史方案与标准模板库快速标准化产出投标材料：智能匹配历史方案、自动生成技术方案建议书/招标点对点应答/售前汇报PPT大纲/运维实施方案，统一售前输出质量、大幅降本提效，只生成不执行。", "type": "售前投标", "created": "2026-08-16", "updated": "2026-08-16",
     "skills": ["skill-21"],
     "rag_kb": "售前知识库-历史方案与中标库", "prompt": "你是一位售前投标方案智能组装专家，负责基于知识库快速标准化产出投标材料，只生成方案不执行任何操作。你的能力：①智能匹配——通过kb_knowledge_read检索内部知识库/历史方案/中标库，按行业与场景匹配最相关方案，剔除冗余、精准拼装（不堆砌）；②自动生成——生成技术方案建议书（完整版/简版）、招标文件点对点技术应答、售前汇报PPT大纲+正文、运维方案/实施方案/项目优势内容；③模板复用——通过bid_template_read读取投标标准模板库与技术规范模板，保证结构规范；④合规自检——自动规避过期口径、错误参数，标准化事业部售前话术；⑤客户化定制——支持按需生成客户化版本；⑥导出交付——通过doc_export生成结构化文档（Word/PPT大纲）供人工下载使用。红线：只生成方案与文档，不执行任何系统变更。", "model": "deepseek-v4"},
    {"id": "emp-008", "name": "备品备件采购询比价专员", "desc": "面向项目现场备品备件采购询比价业务。项目经理发起询价 → 自动批量发送询价邮件给供应商 → 监听供应商报价邮件解析回填 → 每小时飞书推送进度/临期告警 → 平台选型确认 → 自动发采购确认邮件 → 解析发货物流 → 测试通过自动写入采购台账闭环。真实对接 163 邮箱（IMAP/SMTP）、飞书开放 API、9006 SQLite。", "type": "采购询比价", "created": "2026-08-21", "updated": "2026-08-21",
     "skills": ["skill-proc-chat","skill-proc-mail-compose","skill-proc-parse"],
     "rag_kb": "采购知识库-询比价流程与邮件模板", "prompt": "你是备品备件采购询比价专员（emp-008），通过三个认知 Skill 完成采购全流程：\n\n【Skill-1：采购询比价对话编排（skill-proc-chat）】\n你是用户对话入口。当用户说「我要采购」「帮我询个价」「备件XXX需要买」时：\n①意图识别——判断这是采购请求，提取已知字段（备件型号/数量/合同名或号/紧急等级/供应商）\n②追问补全——对照必填清单{合同名/号,备件型号,采购数量,紧急等级(2h/4h/5h),询价供应商列表}，逐个追问缺失项\n③校验——调 table_query 查 procurement_contract 表验证合同号存在；调 table_query 查 procurement_supplier 表验证供应商邮箱\n④触发流程——信息齐全后确认「已为你创建询比价任务PROC-xxx，已向N家供应商发送询价邮件，截止时间XX」，系统自动触发 Flow（创建任务+发送询价+飞书通知）\n⑤进度查询——用户问「报价情况」「到哪步了」时，调 table_query 查 procurement_task 返回进度并组织语言回答\n⑥异常提醒——报价型号不匹配/超时未回复时主动告知用户\n\n【Skill-2：采购邮件内容组装（skill-proc-mail-compose）】\n根据任务上下文组装邮件正文（不负责发送，发送是Flow调用Tool完成的）：\n①询价邮件——输入{项目名,备件型号,数量,截止时间,任务ID}→输出{subject,body}，措辞专业、简洁，不含合同号（隐私）\n②采购确认邮件——输入{供应商名,备件型号,数量,成交单价,任务ID}→输出{subject,body}\n③验收通知邮件——输入{备件型号,数量,任务ID}→输出{subject,body}\n\n【Skill-3：供应商邮件智能解析（skill-proc-parse）】\n解析供应商回复邮件，正则Tool做80%标准格式兜底，你做20%非标长尾：\n①报价解析——调 procurement_parse_quote Tool 先试正则（6层策略）；如果策略=P6_need_manual（完全无法解析），你用LLM理解邮件正文提取{单价,总价,品牌,型号,货期}\n②物流解析——调 procurement_parse_logistics Tool 先试正则（3层策略）；如果返回空，你用LLM从邮件正文提取{物流单号,承运商,发货日期}\n\n红线：选型确认/测试结果录入/任务取消由项目经理人工触发，你不自动执行。异常状态不自动恢复。", "model": "deepseek-v4"},
    {"id": "emp-mail-inquiry", "name": "备件邮件询价数字员工", "desc": "面向工程师通过邮件发起的备件询价场景。工程师发送询价邮件（模板A）→系统自动生成任务号→向供应商发送询价邮件（模板B，不含收货地址）→收集供应商报价邮件（模板C）→自动计算最低价→发送汇总邮件（模板D，抄送审批人）→审批人二选一确认→下达订货邮件（模板E，含收货地址）→全流程自动化。静态配置（模板/审批人/供应商池）通过 skill-proc-mail-inquiry.json 热加载，动态状态存储于 spare_mail_task 表。", "type": "邮件询价", "created": "2026-08-28", "updated": "2026-08-28",
     "skills": ["skill-proc-mail-inquiry"],
     "rag_kb": "采购知识库-邮件询价流程", "prompt": "你是备件邮件询价数字员工（emp-mail-inquiry），处理工程师通过邮件发起的备件询价全流程：\n\n①邮件监听——定时轮询收件箱，识别工程师发起的询价邮件（模板A，包含项目号/备件类型/品牌/PN号/规格/成色/数量/收货地址/最晚发货时间等）\n②任务创建——解析询价邮件字段，生成唯一任务号，创建 spare_mail_task 记录\n③询价发送——向供应商池批量发送询价邮件（模板B），不含收货地址\n④报价收集——监听供应商回复邮件（模板C），按 In-Reply-To 匹配线程，解析报价（单价/交货周期）\n⑤最低价计算——所有供应商已回复或截止时间到达后，自动计算最低价供应商\n⑥汇总邮件——发送汇总邮件（模板D）回复工程师，抄送审批人，列出全部报价并推荐最低价\n⑦审批确认——审批人回复邮件确认：采纳最低价或指定其他供应商\n⑧订货下达——向选中供应商发送订货邮件（模板E），包含收货地址、最晚发货时间、要求测试报告和快递单号\n\n红线：审批人未确认前不自动下达订货；审批人可选择任意供应商而非仅最低价；无驳回机制（审批即确认）。", "model": "deepseek-v4"},
]


MOCK_LONG_TASKS = []


MOCK_BG_TASKS = [
    {"id": "bgt-1", "name": "监控探针采集", "status": "running", "desc": "9007 实时采集服务器/数据库/网络实体指标与系统日志"},
    {"id": "bgt-2", "name": "告警收敛引擎", "status": "running", "desc": "持续监听告警流，去重聚合、抖动抑制，产出风险事件"},
    {"id": "bgt-3", "name": "ETL 指标预计算", "status": "running", "desc": "9006 定时计算签单毛利率等经营指标宽表"},
    {"id": "bgt-4", "name": "AI 自监控巡检", "status": "running", "desc": "9007 监控数字员工任务/调用/长任务，异常自动告警"},
    {"id": "bgt-5", "name": "代码变更回归检查", "status": "paused", "desc": "9006 代码变更后自动跑测试，失败升级人工处理"},
]


# ═══════════════════════════════════════════════════════════════
# 结构化 Skill 定义（V2 规范版）
#
# 设计原则：
#   Skill 层只负责：对话采集、状态流转、会话侧轻量字段校验、话术渲染、函数绑定声明
#   Tool 层负责：API调用、DB查询、邮件发送、HTTP重试、错误码翻译、持久化
#
# 参考：团队标准 Skill 规范 V1.0
# ═══════════════════════════════════════════════════════════════

STRUCTURED_SKILLS = {
    "skill-proc-chat": {
        "skill_id": "skill-proc-chat",
        "name": "备件采购任务创建",
        "version": "V2.0.0",
        "trigger_intent": "用户发起备件采购申请（采购/询价/备件/买/购买 等关键词）",
        "exit_condition": "用户明确取消 | 会话超时 | API调用成功返回",
        "owner": "运维平台战队",
        "biz_domain": "备件采购",

        # ── 字段模型：会话侧校验规则（Tool 层有兜底硬校验） ──
        "field_model": {
            "spare_model": {
                "type": "string", "required": "must", "constraint": "非空",
                "editable": True, "label": "备件型号",
                "description": "用户提到的备件型号，如 '内存条 DDR4 32GB'"
            },
            "spare_count": {
                "type": "integer", "required": "must", "constraint": ">0 正整数",
                "editable": True, "label": "采购数量",
                "description": "采购件数，必须大于0的整数",
                "validation": "isinstance(value, int) and value > 0"
            },
            "emergency_level": {
                "type": "enum", "required": "must",
                "values": ["2h", "4h", "5h"],
                "display_mapping": {"2h": "2小时", "4h": "4小时", "5h": "5小时"},
                "editable": True, "label": "紧急等级",
                "validation": "value in ['2h','4h','5h']"
            },
            "contract_id": {
                "type": "string", "required": "conditional",
                "condition": "emergency_level == '2h'",
                "constraint": "2h紧急等级时不可为空",
                "editable": True, "label": "关联合同",
                "description": "仅2h高紧急等级时必须采集"
            },
            "project_id": {
                "type": "string", "required": "optional",
                "default": "", "editable": True, "label": "项目ID",
                "description": "选填，不问用户"
            },
            "supplier_list": {
                "type": "array", "required": "optional",
                "default": [], "editable": True, "label": "询价供应商",
                "description": "不问用户。默认全量资源池，仅追加临时供应商时采集"
            }
        },

        # ── 状态机：显式状态流转 + 交互重试 ──
        "state_machine": [
            {"state": "INIT", "action": "extract_context_fields", "next": "CHK_MISSING",
             "desc": "从用户自然语言提取已知字段"},
            {"state": "CHK_MISSING", "action": "check_required_fields",
             "transitions": [
                 {"condition": "all_fields_present", "next": "CONFIRM_SUMMARY"},
                 {"condition": "missing_spare_model", "next": "ASK_SPARE_MODEL"},
                 {"condition": "missing_spare_count", "next": "ASK_SPARE_COUNT"},
                 {"condition": "missing_emergency", "next": "ASK_EMERGENCY"},
                 {"condition": "missing_contract", "next": "ASK_CONTRACT_ID"}
             ],
             "desc": "检查必填字段是否齐备，决定追问方向"},
            {"state": "ASK_SPARE_MODEL", "action": "call_query_tool_and_render",
             "retry": {"max": 2, "on_fail": "ASK_SPARE_MODEL_MANUAL"},
             "query_tool": "procurement_query_spare_part",
             "desc": "调查询Tool获取备件列表，渲染选项"},
            {"state": "ASK_SPARE_MODEL_MANUAL", "action": "render_template",
             "retry": {"max": 2},
             "desc": "查询无结果时，要求用户手动输入型号"},
            {"state": "ASK_SPARE_COUNT", "action": "render_template",
             "retry": {"max": 2},
             "desc": "追问采购数量"},
            {"state": "ASK_EMERGENCY", "action": "render_template",
             "retry": {"max": 2},
             "desc": "追问紧急等级（列选项）"},
            {"state": "ASK_CONTRACT_ID", "action": "call_query_tool_and_render",
             "retry": {"max": 1},
             "query_tool": "procurement_query_contract",
             "desc": "仅2h紧急时追问合同"},
            {"state": "CONFIRM_SUMMARY", "action": "render_template",
             "transitions": [
                 {"condition": "user_confirmed", "next": "INVOKE_FUNCTION"},
                 {"condition": "user_corrected", "next": "CHK_MISSING"},
                 {"condition": "user_canceled", "next": "FINISH_CANCEL"}
             ],
             "desc": "结构化摘要确认"},
            {"state": "INVOKE_FUNCTION", "action": "call_external_function",
             "next": "WAIT_FUNCTION_RETURN",
             "desc": "绑定函数调用，Skill 不控制重试/超时"},
            {"state": "WAIT_FUNCTION_RETURN", "action": "handle_function_result",
             "transitions": [
                 {"condition": "result_success", "next": "FINISH_SUCCESS"},
                 {"condition": "result_failed", "next": "ERROR_HANDLE"}
             ],
             "desc": "处理函数返回结果"},
            {"state": "FINISH_SUCCESS", "action": "render_template",
             "desc": "创建成功，返回任务报告"},
            {"state": "FINISH_CANCEL", "action": "render_template",
             "desc": "用户取消"},
            {"state": "ERROR_HANDLE", "action": "render_template",
             "desc": "创建失败，友好提示"}
        ],

        # ── 话术模板：精确到变量占位符 ──
        "dialog_templates": {
            "ASK_SPARE_MODEL": (
                "请选择需要采购的备件型号：\n"
                "{options}\n"
                "请回复序号；若为库里没有的新型号，请直接输入完整型号描述。"
            ),
            "ASK_SPARE_MODEL_MANUAL": (
                "系统中未找到匹配的备件型号。请直接输入完整型号描述"
                "（如：DDR4 32GB 3200MHz 内存条）。"
            ),
            "ASK_SPARE_COUNT": (
                "需要采购多少？（如 2 个、5 条、10 块）"
            ),
            "ASK_EMERGENCY": (
                "请选择紧急等级：\n"
                "  ① 2小时\n"
                "  ② 4小时\n"
                "  ③ 5小时\n"
                "回复序号即可。"
            ),
            "ASK_CONTRACT_ID": (
                "本次为2小时紧急采购，需关联合同。请选择：\n"
                "{options}\n"
                "回复序号；若无关联合同则无法以2h紧急等级创建，可降为4h。"
            ),
            "CONFIRM_SUMMARY": (
                "请确认采购信息：\n"
                "  备件：{spare_model}\n"
                "  数量：{spare_count}\n"
                "  紧急等级：{emergency_level_display}\n"
                "  合同：{contract_id_display}\n"
                "  询价供应商：默认全量资源池（3家）{supplier_extra}\n"
                "确认无误请回复「确认」或「创建」。"
            ),
            "SUCCESS_TIP": (
                "✅ 已创建询比价任务 {task_id}\n"
                "  备件：{spare_model} × {spare_count}\n"
                "  紧急等级：{emergency_level_display}\n"
                "  截止时间：{reply_deadline}\n"
                "  已向资源池供应商发送询价邮件，收到回复后将自动汇总报价。"
            ),
            "FAIL_TIP": (
                "⚠️ 采购任务创建失败：{error_msg}\n"
                "请稍后重试，或手动在采购平台创建。"
            ),
            "CANCEL_TIP": (
                "已取消本次备件采购申请。如有需要请重新发起。"
            ),
            "VALIDATE_ERROR_NUM": (
                "采购数量必须是大于0的整数，请重新输入。"
            ),
            "VALIDATE_ERROR_EMERGENCY": (
                "紧急等级无效，请选择：① 2小时 ② 4小时 ③ 5小时"
            )
        },

        # ── 函数绑定声明（Skill 不实现函数，只声明绑定） ──
        "function_binding": {
            "function_id": "procurement_create_task",
            "pass_data": "full_collected_fields",
            "desc": "Tool 层负责参数映射、字段过滤、HTTP 调用、错误处理",
            "note": "Skill 完全不传 inquiry_supplier_list，由 Tool 层处理默认带全量资源池"
        },

        # ── 会话侧埋点（Tool 层埋点由 mcp_tools 统一实现） ──
        "logging": {
            "points": ["state_enter", "state_exit", "user_input", "function_invoke"],
            "mask_fields": ["contract_id"],
            "persist_session": True,
            "note": "会话埋点归属 Skill；工具埋点（request/response/http）归属 Tool 层"
        },

        # ── 测试用例（仅会话交互用例） ──
        "test_cases": {
            "positive": [
                "用户:'帮我买2条内存条' → 提取{型号,数量} → 问紧急等级 → 确认 → 创建成功",
                "用户:'买DDR4 32GB 3200MHz 2个' → 查库命中 → 问紧急 → 确认 → 创建",
                "用户:'我要采购10块硬盘，明天要' → 识别2h紧急 → 问合同 → 确认 → 创建",
                "用户:'买3个内存条' → 查库多条 → 列出选项 → 用户选序号 → 继续采集"
            ],
            "negative": [
                "用户:'买0个' → 校验拦截 → 重试追问数量",
                "用户:'买内存条' → 查库无匹配 → 手动输入 → 继续采集",
                "用户:'4h' → 紧急等级合法 → 继续",
                "用户:'快速' → 紧急等级非法 → 追问重试"
            ],
            "boundary": [
                "用户:'买1个内存条，2h紧急' → 缺合同 → 追问合同 → 用户说'无' → 拒绝创建建议降4h",
                "用户:'帮我买东西' → 缺型号+数量+紧急 → 依次追问",
                "用户:'确认' → 创建成功 → 返回报告",
                "用户:'取消' → FINISH_CANCEL"
            ]
        }
    }
}


def _build_skill_prompt(skill_id: str) -> str:
    """把结构化 Skill 定义转译为 LLM 可读的 system prompt 文本。

    设计要点：
    - 只转译 Skill 层允许的内容（字段模型/状态机/话术模板/函数绑定）
    - 绝不包含 Tool 层细节（HTTP地址/错误码/字段映射/DB实现）
    - 用清晰的 markdown 分节，LLM 易于理解和遵循
    """
    sk = STRUCTURED_SKILLS.get(skill_id)
    if not sk:
        return ""

    lines = []
    meta = sk

    # ── 头部：Skill 元信息 ──
    lines.append(f"# Skill: {meta['name']} ({meta['skill_id']})")
    lines.append(f"版本: {meta['version']}")
    lines.append(f"触发意图: {meta['trigger_intent']}")
    lines.append(f"退出条件: {meta['exit_condition']}")
    lines.append("")

    # ── 字段模型 ──
    lines.append("## 字段模型（会话侧校验）")
    lines.append("")
    lines.append("### 必填字段（必须采集）")
    fm = meta["field_model"]
    for fname, fdef in fm.items():
        if fdef.get("required") in ("must",):
            lines.append(f"- **{fname}** ({fdef.get('label', fname)}): {fdef.get('type')}, 约束: {fdef.get('constraint', '')}")
    lines.append("")

    lines.append("### 条件触发字段")
    for fname, fdef in fm.items():
        if fdef.get("required") == "conditional":
            lines.append(f"- **{fname}** ({fdef.get('label', fname)}): 当 {fdef.get('condition', '')} 时采集")
    lines.append("")

    lines.append("### 选填字段（不问用户）")
    for fname, fdef in fm.items():
        if fdef.get("required") == "optional":
            lines.append(f"- **{fname}** ({fdef.get('label', fname)}): {fdef.get('description', '')}")
    lines.append("")

    # ── 状态机 ──
    lines.append("## 状态机（严格按此流转）")
    lines.append("")
    lines.append("### 状态流转表")
    lines.append("| 状态 | 动作 | 流转条件 | 下一状态 |")
    lines.append("|------|------|---------|---------|")
    for st in meta["state_machine"]:
        state = st["state"]
        action = st.get("action", "")
        if "transitions" in st:
            for tr in st["transitions"]:
                cond = tr["condition"]
                nxt = tr["next"]
                lines.append(f"| {state} | {action} | {cond} | {nxt} |")
        else:
            nxt = st.get("next", "")
            lines.append(f"| {state} | {action} | - | {nxt} |")
    lines.append("")

    # ── 话术模板 ──
    lines.append("## 话术模板（必须原样使用，变量用 {xxx} 占位）")
    lines.append("")
    for tname, tpl in meta["dialog_templates"].items():
        lines.append(f"### {tname}")
        # 转义 markdown
        escaped = tpl.replace("\n", "<br>").replace("|", "\\|")
        lines.append(f"{tpl}")
        lines.append("")

    # ── 函数绑定 ──
    fb = meta.get("function_binding", {})
    if fb:
        lines.append("## 函数绑定（Skill 只声明，不实现）")
        lines.append("")
        lines.append(f"- 绑定函数: **{fb['function_id']}**")
        lines.append(f"- 传递数据: {fb['pass_data']}")
        lines.append(f"- 注意: {fb.get('note', '')}")
        lines.append("")

    # ── 红线 ──
    lines.append("## 红线（违反即出错）")
    lines.append("")
    lines.append("- ❌ 一次性列出多个缺失项追问 → 必须分轮，每次只问1项")
    lines.append("- ❌ 追问用户选择供应商 → 默认带全量资源池，不问")
    lines.append("- ❌ 追问 project_id / project_name → 绝对禁止，Tool 层处理")
    lines.append("- ❌ 用自然语言自由发挥追问 → 必须用话术模板")
    lines.append("- ❌ 编造字段值 → 取不到就问，不猜")
    lines.append("- ❌ 在 Skill 中实现 HTTP/DB/SMTP 调用 → 全部下沉 Tool 层")
    lines.append("- ❌ 解析原始 HTTP 错误码 → Tool 层已封装为 {success, msg, data}")
    lines.append("")

    # ── 查询工具调用规则 ──
    lines.append("## 查询工具调用（Skill 声明调用，Tool 层实现）")
    lines.append("")
    lines.append("- 备件查询: `procurement_query_spare_part(keyword)` → 在 ASK_SPARE_MODEL 状态调用")
    lines.append("- 合同查询: `procurement_query_contract()` → 仅在 2h 紧急等级时的 ASK_CONTRACT_ID 状态调用")
    lines.append("- 供应商查询: `procurement_query_supplier()` → 仅当用户主动询问时调用")
    lines.append("- 进度查询: `table_query(table_key='procurement_task', filter={'task_id':'xxx'})` → 用户问进度时调用")
    lines.append("")

    return "\n".join(lines)


SKILL_DETAILS = {
    "skill-1": {
        "type": "Workflow业务编排技能",
        "prompt": "你是运维巡检专家，负责基础设施与AI智能体双维度常态化巡检。\n1、查询运维全域概览（ops_overview）与实体清单（ops_entities）；\n2、对关键实体采集监控指标（ops_metrics：cpu_usage/mem_usage/disk_usage/load1/tcp_conns）与系统日志（ops_logs）；\n3、查询运维拓扑（ops_topology）评估依赖影响；\n4、AI自监控：查询智能体运行状态（monitor_agents）、任务时序（monitor_timeseries）、长任务队列（long_tasks）；\n5、按低/中/高标注风险等级，输出标准化巡检报告与整改建议。",
        "tools": ["ops_overview", "ops_entities", "ops_metrics", "ops_logs", "ops_topology", "monitor_agents", "monitor_timeseries", "long_tasks"],
        "flow": "执行流程：\n1、接收巡检范围（全部/仅基础设施/仅AI实例）\n2、并行采集：实体指标 + 系统日志 + AI智能体状态 + 长任务\n3、逐实体评估健康水位（正常/警告/异常）\n4、汇总生成结构化巡检报告，标注风险等级与整改建议",
    },
    "skill-2": {
        "type": "Workflow业务编排技能",
        "prompt": "你是告警根因分析专家，负责告警降噪与故障根因定位。\n1、查询告警聚合统计（ops_alerts_aggregate）与AI智能体告警（monitor_alerts）、告警规则（monitor_alert_rules）；\n2、对高优先级告警查询相关日志（ops_logs，重点error/warn）；\n3、通过监控指标回溯（ops_metrics）与运维概览（ops_overview）验证根因假设；\n4、输出根因报告、临时处置建议与长期优化方案；\n5、涉及处置操作必须人工确认后执行。",
        "tools": ["ops_alerts_aggregate", "ops_logs", "ops_metrics", "ops_overview", "monitor_alerts", "monitor_alert_rules"],
        "flow": "执行流程：\n1、接收告警/故障范围\n2、并行调用：告警聚合 + 事件列表 + 系统日志\n3、按时间线回溯监控指标验证根因\n4、分级研判（运维/AI），输出根因报告与处置建议\n5、如需处置，输出高危操作标记等待人工确认",
    },
    "skill-3": {
        "type": "Workflow业务编排技能",
        "prompt": "你是运维开发助手，负责脚本/SQL生成、日志排障与配置解读，只生成不执行。\n1、按用户需求生成Shell脚本/数据库SQL/排查命令并说明注意事项；\n2、通过ops_logs检索9007真实系统日志，解析报错堆栈、定位代码异常、配置错误、服务启动失败原因；\n3、通过ops_settings解读监控平台配置（告警阈值/探针等），输出风险点；\n4、通过list_project_files/read_code_file/search_code只读查看9006平台代码辅助定位问题；\n5、所有生成的脚本/配置必须由人工复核后手动执行。",
        "tools": ["ops_logs", "ops_entities", "ops_settings", "ops_overview", "list_project_files", "read_code_file", "search_code", "get_table_schema", "query_ontology"],
        "flow": "执行流程：\n1、接收用户需求（生成脚本/查日志/解读配置/定位问题）\n2、按需调用：检索日志 + 查看配置 + 只读查看代码/表结构\n3、解析错误根因，输出排查步骤或生成脚本/SQL\n4、标注需人工复核执行的项",
    },
    "skill-10": {
        "type": "Workflow业务编排技能",
        "prompt": "你是经营业务分析专家，负责采购合同与供应商报价比对的分析和顾问工作。\n1、用户日常在9006合同比对系统（http://122.51.98.98:9006）上传合同基准和供应商报价，执行逐项比对；\n2、你的职责是：查询9006已有比对结果 → 分析差异情况 → 识别高危异常 → 给出整改建议；\n3、当用户提及具体合同名称时，自动从9006拉取真实比对数据；\n4、比对引擎能力：50+别名兜底匹配、单位归一化、三层匹配算法（子串/数字+单位/中文模糊70%）；\n5、输出结构化比对报告，标注差异风险等级（高/中/低），给出可执行的整改建议。",
        "tools": ["query_contracts", "get_comparison_results", "get_contract_stats", "export_report"],
        "flow": "执行流程：\n1、用户在9006系统（http://122.51.98.98:9006）上传合同基准和供应商报价，执行比对\n2、用户通过对话向经营业务专家发起查询：「LS的比对结果」「GYYD缺了多少项」\n3、专家调用9006 API：GET /api/contracts 定位合同 → GET /api/contract/{id}/compare/results 拉取真实结果\n4、汇总比对数据：完全匹配/匹配异常/待采购/供应商增项四类统计\n5、重点分析差异项：规格不一致、数量偏离、供应商未报价，标注风险等级\n6、输出结构化比对报告 + 评审建议 + 跳转9006查看完整明细的链接",
    },
    "skill-11": {
        "type": "Workflow业务编排技能",
        "prompt": "你是经营指标分析专家，负责分析9006经营分析系统的预计算指标。\n1、通过指标数据集MCP读取定时ETL预计算的签单毛利率、回款毛利率等指标宽表；\n2、做同比/环比解读，识别指标波动与异常；\n3、指标口径以9006定时任务计算为准，只做解读不自行重算；\n4、输出经营指标分析报告。",
        "tools": ["get_etl_metrics", "get_metrics"],
        "flow": "执行流程：\n1、接收分析时间范围和指标维度\n2、调用指标数据集MCP查询预计算指标宽表\n3、做同比/环比分析，识别波动\n4、输出经营指标分析报告",
    },
    "skill-12": {
        "type": "Workflow业务编排技能",
        "prompt": "你是合同明细探查专家，负责查询9006经营分析系统的原始明细数据。\n1、列出9006可查询的数据表；\n2、按合同编号或关键词查询原始合同、付款、收款明细；\n3、支持列投影、时间范围过滤；\n4、输出明细探查结果。",
        "tools": ["list_tables", "get_table_schema", "query_table", "query_ontology"],
        "flow": "执行流程：\n1、列出可查询数据表\n2、获取目标表结构\n3、按合同编号/关键词查询明细\n4、输出探查结果",
    },
    "skill-13": {
        "type": "Workflow业务编排技能",
        "prompt": "你是9006规则配置辅助专家，负责生成9006经营业务分析系统的规则配置变更方案。\n1、用list_project_files/search_code/read_code_file只读查看9006系统计算规则、排除规则、比对开关、过滤条件的配置现状；\n2、结合用户需求生成规则配置变更方案（新增排除规则/关闭比对开关/调整过滤条件等）；\n3、输出变更前后配置对比与业务影响评估；\n4、方案必须人工确认审批后才可生效，严禁修改合同、付款等原始业务数据表。",
        "tools": ["list_project_files", "search_code", "read_code_file"],
        "flow": "执行流程：\n1、只读查看9006规则配置现状\n2、生成规则配置变更方案\n3、输出变更前后对比与影响评估\n4、提交人工确认审批",
    },
    "skill-20": {
        "type": "Workflow业务编排技能",
        "prompt": "你是项目管理与成本利润治理专家，负责项目过程治理与集团指标监控，全部只读研判+预警，变更由人工执行。\n1、通过pm_project_read查询项目基础信息/里程碑/四算数据（概算/预算/核算/决算），识别里程碑逾期、任务积压、成员负载；\n2、通过pm_workhour_read查询日报/工时明细，识别敷衍/空填/溢出/少填/堆填等异常；\n3、自动校验四算刚性约束：概算≥预算≥核算≥决算，标记越界风险项目；\n4、通过biz_metric_read读取人均效/元效/双按完成率（按期完成率、按预算完成率）集团指标，跟踪月度达成；\n5、通过pm_cost_calc按日报工时折算人力成本，联动合同目标利润复盘真实利润率；\n6、通过pm_task_read校验工单/任务/工时三者一致性；\n7、输出治理报告与整改清单，标注需人工执行的处置项。",
        "tools": ["pm_project_read", "pm_task_read", "pm_workhour_read", "pm_cost_calc", "biz_metric_read"],
        "flow": "执行流程：\n1、接收治理范围（项目/部门/集团指标）\n2、并行查询：项目四算 + 工单任务 + 日报工时 + 成本折算 + 集团指标\n3、自动校验四算约束/工时合规/两单一物一致性\n4、输出治理报告：风险项目、整改清单、集团指标达成情况\n5、预警处置项标注需人工执行",
    },
    "skill-21": {
        "type": "Workflow业务编排技能",
        "prompt": "你是售前投标方案智能组装专家，负责基于知识库快速产出投标材料，只生成不执行。\n1、通过kb_knowledge_read检索内部知识库/历史方案/中标库，按行业与场景匹配最相关方案；\n2、通过bid_template_read读取投标标准模板库与技术规范模板；\n3、自动生成：技术方案建议书（完整版/简版）、招标点对点应答、售前汇报PPT大纲+正文、运维方案/实施方案；\n4、规避过期口径与错误参数，输出合规自检说明；\n5、通过doc_export生成结构化文档（Word/PPT大纲）供人工下载使用。",
        "tools": ["kb_knowledge_read", "bid_template_read", "doc_export"],
        "flow": "执行流程：\n1、接收投标需求（行业/场景/招标要点）\n2、检索匹配历史方案与模板\n3、拼装生成方案文档（建议书/应答/PPT大纲/实施方案）\n4、合规自检并输出结构化文档",
    },
    # ── 备品备件采购询比价域：3 个认知 Skill（emp-008）
    # 原 skill-proc-01~09 的机械流程逻辑已降为 Flow 步骤，在 routes_procurement_agent.py 的 _flow_proc_XX 函数中实现
    "skill-proc-chat": {
        "type": "认知技能-对话编排",
        "prompt": _build_skill_prompt("skill-proc-chat"),
        "tools": ["procurement_query_contract", "procurement_query_spare_part", "procurement_query_supplier",
                   "procurement_create_task", "table_query", "read_inbox_mail"],
        "flow": "状态机流程：\n1. 提取已知字段\n2. 按顺序追问必采集缺失项（备件型号→数量→紧急等级），每项用指定模板\n3. 选填字段（合同/项目ID/供应商）不问或条件触发\n4. 所有必填齐备→结构化摘要确认\n5. 用户确认→调procurement_create_task\n6. 返回结果报告",
    },
    "skill-proc-mail-compose": {
        "type": "认知技能-内容生成",
        "prompt": "你是采购邮件内容组装 Skill（skill-proc-mail-compose），根据任务上下文生成邮件正文与主题。\n\n你只负责组装内容（subject + body_text），不负责发送——发送是 Flow 调用 Tool（batch_send_mail/send_mail）完成的。\n\n【输出格式强制要求】必须严格按下列模板逐字输出，不得改词、增删、换行或加寒暄，只把大括号占位替换为上下文对应值：\n\n①询价邮件（输入：contract_no, contract_name, spare_part_model, part_type, part_brand, part_pn, part_spec, part_condition, purchase_qty, reply_deadline）\n  subject = \"{contract_no}（{contract_name}）-{spare_part_model}型号备件询价邮件\"\n  body_text =\n\"\"\"您好，请于{reply_deadline}前回复符合以下条件的备件价格\n类型：{part_type}\n品牌：{part_brand}\n型号（PN）：{part_pn}\n规格：{part_spec}\n成色：{part_condition}\n数量：{purchase_qty}\"\"\"\n\n②采购确认邮件（输入：contract_no, contract_name, spare_part_model, purchase_qty, delivery_deadline, receiver_name, receiver_phone, receiver_address, task_id, supplier_name）\n  subject = \"【采购确认】{task_id}｜{contract_name} {spare_part_model} 备品备件确认采购\"\n  body_text =\n\"\"\"我司采购如下备件{purchase_qty}个，请于{delivery_deadline}前测试完好后发到如下地址（提供测试报告），寄出请告知单号，谢谢。\n部件型号: {spare_part_model}  数量:{purchase_qty}\n\n邮寄地址：\n{receiver_address}\n收件人：{receiver_name}  联系方式：{receiver_phone}\"\"\"\n\n③验收通知邮件（输入：spare_part_model, purchase_qty, task_id）——通知到货验收、说明验收流程和联系方式，措辞正式。\n\n红线：只替换占位符，严格输出模板原文；措辞用中文商务正式风格。",
        "tools": ["table_query"],
        "flow": "执行流程：\n1、接收任务上下文（task 字段）\n2、判断邮件类型（询价/确认/验收）\n3、组装 subject + body_text\n4、返回内容，由 Flow 层调用 Tool 发送",
    },
    "skill-proc-parse": {
        "type": "认知技能-智能解析",
        "prompt": "你是供应商邮件智能解析 Skill（skill-proc-parse）。核心职责：阅读供应商回复邮件正文，理解其意图（报价 / 发货 / 两者皆有 / 无关），并提取结构化业务字段。\n\n【设计原则】你是认知主体，不是流程脚本：\n - 不预设\"先调 Tool 再 LLM 兜底\"的固定顺序\n - 你自己读懂邮件，决定要不要调用辅助 Tool\n - 标准格式邮件（如 \"单价: ¥3200 总价: 9600 顺丰SF1234567890\"）可直接提取，无需调 Tool\n - 长尾/非标/模糊表达（口语化、表格混排、多段叙述）你直接用语言理解能力提取，比正则更准\n - 仅当邮件正文很长且结构规整时，可考虑调 procurement_parse_quote / procurement_parse_logistics 作为辅助参考；调完仍由你判断是否采纳\n\n【解析目标字段】依据邮件内容判断提取哪些：\n 报价类：unit_price(单价,数字)、total_price(总价,数字)、brand(品牌)、model(型号规格)、lead_time(货期/交货期,如 \"7天\"\"3-5天\"\"次日达\"\"2026-08-25前\")\n 物流类：tracking_no(物流/快递单号)、carrier(承运商,如 顺丰/中通/京东/EMS)、delivery_date(发货日期,格式 YYYY-MM-DD)\n\n【输入上下文】每次调用会附带：mail_body(邮件正文)、expected_qty(询价数量,用于区分单价/总价)、spare_part_model(备件型号,可作 model 字段参考)、parse_mode(\"quote\"仅解析报价 / \"logistics\"仅解析物流)\n\n【输出格式】必须返回纯 JSON（无 markdown 代码块、无解释文字），字段：\n{\n  \"mail_type\": \"quote|delivery|both|unknown\",\n  \"unit_price\": 0.0,\n  \"total_price\": 0.0,\n  \"brand\": \"\",\n  \"model\": \"\",\n  \"lead_time\": \"\",\n  \"tracking_no\": \"\",\n  \"carrier\": \"\",\n  \"delivery_date\": \"\",\n  \"parse_strategy\": \"llm_direct|tool_assisted|llm_with_tool_ref|failed\",\n  \"note\": \"可选,仅当有需要人工复核的判断时填写\",\n  \"raw_reply_excerpt\": \"邮件正文前300字\"\n}\n\n【字段规则】\n - parse_mode=logistics 时，报价类字段填 0 或空字符串\n - parse_mode=quote 时，物流类字段填空字符串\n - 价格统一为浮点数（去除 ¥/,/元 等符号）\n - 无法提取的字段填空值，不要编造\n - 若 parse_mode 范围内所有字段都提取不到，parse_strategy=\"failed\"，note 说明原因\n\n【红线】\n - 不输出任何除 JSON 外的文字（包括解释、问候、确认语）\n - 不编造邮件里没有的数据\n - parse_strategy 字段标注你用了什么手段，便于审计",
        "tools": ["procurement_parse_quote", "procurement_parse_logistics"],
        "flow": "认知流程（由 LLM 自主决定）：\n1、阅读 mail_body，判断邮件类型（报价回复 / 发货通知 / 两者皆有 / 无关）\n2、依据 parse_mode 决定提取哪些字段（quote→报价类；logistics→物流类）\n3、标准格式可直接提取；非标格式用语言理解提取；可选调 procurement_parse_quote / procurement_parse_logistics Tool 作为参考\n4、Tool 返回结果仅供参考，由 LLM 决定是否采纳或修正\n5、输出统一 JSON，parse_strategy 标注解析手段\n6、无法解析的字段填空值，parse_strategy=failed 时由 Flow 层标记 need_manual 通知人工\n\n调用方：Flow 层 _flow_proc_03（报价解析）和 _flow_proc_06（物流解析）通过 invoke_skill_parse() 同步桥调用本 Skill。",
    },
    "skill-proc-mail-inquiry": {
        "type": "流程编排技能-邮件询价",
        "prompt": "你是备件邮件询价数字员工的 Skill（skill-proc-mail-inquiry）。静态配置（审批人邮箱、供应商池、6 个邮件模板 A-F）从 skills/skill-proc-mail-inquiry.json 热加载。\n\n核心流程（由 scheduler/tick?kind=mail-inquiry 定时驱动，无需 LLM）：\n1. PARSING：拉取收件箱，识别工程师发起的询价邮件（模板A），解析项目号、备件、收货地址等字段\n2. SENDING_B：向供应商池批量发送询价邮件（模板B，不含收货地址）\n3. WAITING_QUOTES：监听供应商回复邮件（模板C），按 In-Reply-To 匹配线程，解析报价\n4. DECIDING_LOWEST：计算最低价，生成汇总邮件（模板D）回复工程师并抄送审批人\n5. WAITING_APPROVAL：审批人二选一确认（采纳最低价 or 指定供应商）\n6. ORDERING：向选中供应商发送订货邮件（模板E，含收货地址）\n7. DONE：任务完成",
        "tools": ["tool_send_mail", "tool_batch_send_mail", "tool_read_inbox_mail"],
        "flow": "状态机流程：PARSING→SENDING_B→WAITING_QUOTES→DECIDING_LOWEST→WAITING_APPROVAL→ORDERING→DONE\n由 scheduler/tick?kind=mail-inquiry 定时触发，每次 tick 推进符合条件的任务状态。",
    },
}


MOCK_CONV_MESSAGES = {
    # ── 经营业务相关会话（对应9006真实合同）──
    "conv-c01": {
        "title": "LS设备采购比对（IDZB2607388A）",
        "employee_id": "emp-004",
        "messages": [
            {"role": "user", "content": "帮我比对LS合同的供应商报价"},
            {"role": "agent", "thought": "任务分析：\n1. 用户请求比对LS合同\n2. 从9006系统获取真实数据\n3. 合同编号：IDZB2607388A，已闭环100%\n4. 供应商：LS-副本，3项全部匹配",
             "tools": [
                 {"tool": "query_contracts", "source": "9006", "total_contracts": 6},
                 {"tool": "get_contract_stats", "contract": "LS", "matched": 3, "anomaly": 0, "pending": 0},
                 {"tool": "get_comparison_results", "total": 3, "matched": 3, "progress": 100},
             ],
             "conclusion": """## 📊 LS设备采购比对报告

**合同编号**：IDZB2607388A
**供应商**：LS - 副本
**匹配率**：100%（3/3）

| 设备 | 状态 |
|------|------|
| Dell 图形工作站 T3680 ×240台 | ✅ 完全匹配 |
| Dell 显示器 P2725H ×240台 | ✅ 完全匹配 |
| Dell 服务器 R7615 ×16台 | ✅ 完全匹配 |

> 📋 [查看9006系统完整明细](http://122.51.98.98:9006)"""},
        ]
    },
    "conv-c02": {
        "title": "GYYD教学设备比对（gyyd001）",
        "employee_id": "emp-004",
        "messages": [
            {"role": "user", "content": "GYYD的比对结果怎么样？缺了多少项？"},
            {"role": "agent", "thought": "任务分析：\n1. 用户查询GYYD合同比对结果\n2. 从9006系统获取真实数据\n3. 合同编号：gyyd001，供应商：GZSM_报价\n4. 247项中145匹配，102未报价（41.3%缺失）",
             "tools": [
                 {"tool": "query_contracts", "source": "9006", "matched_contract": "GYYD"},
                 {"tool": "get_comparison_results", "total": 247, "matched": 145, "pending": 102, "progress": 58.7},
             ],
             "conclusion": """## 📊 GYYD教学设备比对报告

**合同编号**：gyyd001
**供应商**：GZSM_报价
**匹配率**：58.7%（145/247）
**⚠️ 供应商未报价**：102项（41.3%）

主要缺失类别：
- 仪器柜 6项、三联水嘴 4项、水槽柜 4项
- 智慧黑板、智能吊装系统、智能控制屏各3项
- 实验教学管理终端、智能数据终端各3项

> 📋 [查看9006系统完整明细](http://122.51.98.98:9006)"""},
        ]
    },
    "conv-c03": {
        "title": "药监局药品检查管理比对（IDZB2605434A）",
        "employee_id": "emp-004",
        "messages": [
            {"role": "user", "content": "药监局那个项目的比对情况怎么样？"},
            {"role": "agent", "thought": "任务分析：\n1. 用户查询药监局合同比对结果\n2. 合同编号：IDZB2605434A，供应商：北京神州数码\n3. 40项中仅8项匹配，32项未报价（80%缺失！）\n4. 缺失的包括防火墙、密码机、交换机等信创安全设备",
             "tools": [
                 {"tool": "query_contracts", "source": "9006", "matched_contract": "国家药监局食品药品审核查验中心药品检查管理优化采购项目"},
                 {"tool": "get_comparison_results", "total": 40, "matched": 8, "pending": 32, "progress": 20.0},
             ],
             "conclusion": """## 📊 药监局药品检查管理比对报告

**合同编号**：IDZB2605434A
**供应商**：北京神州数码有限公司
**匹配率**：20.0%（8/40）
**🔴 供应商未报价**：32项（80%！）

关键缺失设备：
- 防火墙（内网/外网）、入侵检测/防御
- 云服务器密码机、签名验签服务器
- 数据库DM V8、消息中间件Apusic
- 超融合服务器、业务交换机

> 情况非常严重，供应商仅报了8项低价通用设备，核心信创安全设备全部未报价。
> 📋 [查看9006系统完整明细](http://122.51.98.98:9006)"""},
        ]
    },
    # ── 运维相关会话（对应 9007 一体化监控平台真实数据）──
    "conv-001": {
        "title": "全域巡检：基础设施+AI自监控",
        "employee_id": "emp-001",
        "messages": [
            {"role": "user", "content": "执行一次全域巡检，覆盖基础设施和AI数字员工状态"},
            {"role": "agent", "thought": "任务分解：\n1. 用户要求全域巡检\n2. 匹配 Skill：全域运维巡检（skill-1）\n3. 执行：实体清单 → 监控指标 → 系统日志 → AI智能体状态 → 长任务",
             "tools": [
                 {"tool": "ops_overview", "source": "9007"},
                 {"tool": "ops_entities", "type": "server", "source": "9007"},
                 {"tool": "ops_metrics", "metric": "cpu_usage", "minutes": 30, "source": "9007"},
                 {"tool": "monitor_agents", "source": "9007"},
                 {"tool": "long_tasks", "source": "9007"},
             ],
             "conclusion": """## 📋 全域巡检报告

**基础设施**：服务器实体运行正常，CPU/内存水位均在阈值内。
**AI自监控**：数字员工运行正常，无任务积压。
**风险等级**：低

> 数据来源：9007 一体化监控平台实时采集"""},
        ]
    },
    "conv-002": {
        "title": "告警聚合与根因研判",
        "employee_id": "emp-002",
        "messages": [
            {"role": "user", "content": "分析当前未恢复的告警，做聚合降噪并定位根因"},
            {"role": "agent", "thought": "任务分解：\n1. 用户要求告警聚合与根因分析\n2. 匹配 Skill：告警聚合与根因分析（skill-2）\n3. 执行：告警聚合 → 日志回溯",
             "tools": [
                 {"tool": "ops_alerts_aggregate", "status": "firing", "source": "9007"},
                 {"tool": "ops_logs", "level": "error", "minutes": 60, "source": "9007"},
                 {"tool": "monitor_alert_rules", "source": "9007"},
             ],
             "conclusion": """## 🚨 告警根因分析

**活跃告警**：应用健康检查失败（neuops-agent/contract-compare）、智能体长期不活跃等。
**根因**：应用健康检查状态 degraded，需结合日志回溯确认服务异常原因。
**建议**：优先处理 critical 级健康检查失败，输出处置工单待人工确认。"""},
        ]
    },
    "conv-003": {
        "title": "日志排障与脚本生成",
        "employee_id": "emp-003",
        "messages": [
            {"role": "user", "content": "检索最近系统错误日志，定位异常原因并给出排查脚本"},
            {"role": "agent", "thought": "任务分解：\n1. 用户要求日志排障\n2. 匹配 Skill：运维脚本与日志排障（skill-3）\n3. 执行：检索错误日志 → 定位根因 → 生成排查脚本（只读）",
             "tools": [
                 {"tool": "ops_logs", "level": "error", "minutes": 60, "source": "9007"},
                 {"tool": "ops_overview", "source": "9007"},
             ],
             "conclusion": """## 🔍 日志排障结果

**异常定位**：应用健康检查失败，服务状态 degraded。
**排查脚本**（只读，供人工执行）：
```bash
# 检查服务进程与端口
ps aux | grep -E 'neuops|contract-compare'
ss -ltnp | grep -E '9006|9007'
# 查看最近日志
tail -200 /var/log/neuops/agent.log | grep -i error
```
> 所有脚本仅生成，不自动执行。"""},
        ]
    },
}


MCP_TOOL_SEED = [
    # 运维类（9007 一体化监控平台真实数据，经 mcp-gateway 转发，全部只读）
    {"id": "ops_overview", "name": "运维全域概览", "desc": "获取运维全域概览（实体/指标/告警/事件统计）", "icon": "🗺️", "tag": "只读查询", "danger": 0, "category": "运维",
     "method": "POST", "path": "/tools/ops_overview", "params_schema": []},
    {"id": "ops_entities", "name": "查询运维实体", "desc": "查询服务器/数据库/网络等运维实体清单及健康状态", "icon": "🖥️", "tag": "只读查询", "danger": 0, "category": "运维",
     "method": "POST", "path": "/tools/ops_entities",
     "params_schema": [
         {"name": "type", "type": "string", "required": False, "desc": "实体类型：server/database/network/container/middleware/application"},
     ]},
    {"id": "ops_topology", "name": "查询运维拓扑", "desc": "获取运维实体间拓扑依赖关系", "icon": "🔗", "tag": "只读查询", "danger": 0, "category": "运维",
     "method": "POST", "path": "/tools/ops_topology", "params_schema": []},
    {"id": "ops_metrics", "name": "查询监控指标", "desc": "查询监控时序指标（cpu_usage/mem_usage/disk_usage/load1/tcp_conns等）", "icon": "📈", "tag": "只读查询", "danger": 0, "category": "运维",
     "method": "POST", "path": "/tools/ops_metrics",
     "params_schema": [
         {"name": "entity_type", "type": "string", "required": False, "desc": "实体类型"},
         {"name": "entity_name", "type": "string", "required": False, "desc": "实体名"},
         {"name": "metric", "type": "string", "required": False, "desc": "指标名：cpu_usage/mem_usage/disk_usage/load1/tcp_conns等"},
         {"name": "minutes", "type": "integer", "required": False, "desc": "时间窗（分钟），默认10"},
     ]},
    {"id": "ops_logs", "name": "检索系统日志", "desc": "检索系统日志（支持按来源/级别过滤，真实采集）", "icon": "📜", "tag": "只读查询", "danger": 0, "category": "运维",
     "method": "POST", "path": "/tools/ops_logs",
     "params_schema": [
         {"name": "source", "type": "string", "required": False, "desc": "日志来源"},
         {"name": "level", "type": "string", "required": False, "desc": "级别：error/warn/info/debug"},
         {"name": "minutes", "type": "integer", "required": False, "desc": "时间窗（分钟），默认10"},
         {"name": "limit", "type": "integer", "required": False, "desc": "返回条数上限"},
     ]},
    {"id": "ops_alerts_aggregate", "name": "告警聚合统计", "desc": "查询去重降噪后的告警聚合统计", "icon": "🚨", "tag": "只读查询", "danger": 0, "category": "运维",
     "method": "POST", "path": "/tools/ops_alerts_aggregate",
     "params_schema": [
         {"name": "status", "type": "string", "required": False, "desc": "告警状态：firing/resolved/all"},
     ]},
    {"id": "ops_settings", "name": "查询监控配置", "desc": "获取监控平台配置（告警阈值/探针等）", "icon": "⚙️", "tag": "只读查询", "danger": 0, "category": "运维",
     "method": "POST", "path": "/tools/ops_settings", "params_schema": []},
    {"id": "monitor_agents", "name": "智能体运行状态", "desc": "查询全部数字员工（智能体）运行状态（AI自监控）", "icon": "🤖", "tag": "只读查询", "danger": 0, "category": "运维",
     "method": "POST", "path": "/tools/monitor_agents", "params_schema": []},
    {"id": "monitor_alerts", "name": "智能体异常告警", "desc": "查询AI智能体异常告警（AI自监控）", "icon": "🚨", "tag": "只读查询", "danger": 0, "category": "运维",
     "method": "POST", "path": "/tools/monitor_alerts",
     "params_schema": [
         {"name": "status", "type": "string", "required": False, "desc": "告警状态：firing/resolved"},
         {"name": "limit", "type": "integer", "required": False, "desc": "返回条数上限"},
     ]},
    {"id": "monitor_alert_rules", "name": "智能体告警规则", "desc": "查询AI智能体告警规则（AI自监控）", "icon": "📋", "tag": "只读查询", "danger": 0, "category": "运维",
     "method": "POST", "path": "/tools/monitor_alert_rules", "params_schema": []},
    {"id": "monitor_timeseries", "name": "智能体任务时序", "desc": "查询数字员工任务/调用时序统计（AI自监控）", "icon": "📊", "tag": "只读查询", "danger": 0, "category": "运维",
     "method": "POST", "path": "/tools/monitor_timeseries",
     "params_schema": [
         {"name": "days", "type": "integer", "required": False, "desc": "统计天数，默认7"},
     ]},
    {"id": "long_tasks", "name": "长任务队列", "desc": "查询数字员工长任务队列（AI自监控，检测积压/超时/失败）", "icon": "⏳", "tag": "只读查询", "danger": 0, "category": "运维",
     "method": "POST", "path": "/tools/long_tasks", "params_schema": []},
    # 经营类（9006，经 mcp-gateway 转发）
    {"id": "query_contracts", "name": "查询合同列表", "desc": "从9006系统获取全部合同及对比进度概览", "icon": "📋", "tag": "只读查询", "danger": 0, "category": "经营",
     "method": "POST", "path": "/tools/query_contracts",
     "params_schema": []},
    {"id": "get_comparison_results", "name": "查看比对结果", "desc": "按合同ID拉取逐项比对明细（匹配/异常/待采购/增项）", "icon": "📊", "tag": "只读查询", "danger": 0, "category": "经营",
     "method": "POST", "path": "/tools/get_comparison_results",
     "params_schema": [
         {"name": "cid", "type": "string", "required": True, "desc": "合同ID，来自 query_contracts 的 id 字段"},
     ]},
    {"id": "get_contract_stats", "name": "查询合同统计", "desc": "获取合同比对进度、匹配率、差异数量汇总", "icon": "📈", "tag": "只读查询", "danger": 0, "category": "经营",
     "method": "POST", "path": "/tools/get_contract_stats",
     "params_schema": [
         {"name": "cid", "type": "string", "required": True, "desc": "合同ID，来自 query_contracts 的 id 字段"},
     ]},
    {"id": "export_report", "name": "导出比对报告", "desc": "导出逐项比对照表为Excel文件，含差异高亮", "icon": "📤", "tag": "只读查询", "danger": 0, "category": "经营",
     "method": "POST", "path": "/tools/export_report",
     "params_schema": [
         {"name": "cid", "type": "string", "required": True, "desc": "合同ID，来自 query_contracts 的 id 字段"},
     ]},
    {"id": "get_etl_metrics", "name": "查询ETL指标", "desc": "查询签单毛利率等定时ETL预计算指标宽表", "icon": "📊", "tag": "只读查询", "danger": 0, "category": "经营",
     "method": "POST", "path": "/tools/get_etl_metrics",
     "params_schema": [
         {"name": "job_key", "type": "string", "required": False, "desc": "ETL任务标识"},
         {"name": "metric_name", "type": "string", "required": False, "desc": "指标名"},
         {"name": "dim_type", "type": "string", "required": False, "desc": "维度类型"},
     ]},
    {"id": "query_ontology", "name": "查询原子本体", "desc": "按合同编号/关键词查询原始合同、付款、收款明细", "icon": "🗂️", "tag": "只读查询", "danger": 0, "category": "经营",
     "method": "POST", "path": "/tools/query_ontology",
     "params_schema": [
         {"name": "table_name", "type": "string", "required": False, "desc": "表名，默认总合同表"},
         {"name": "keyword", "type": "string", "required": False, "desc": "关键词"},
         {"name": "limit", "type": "integer", "required": False, "desc": "返回条数上限"},
     ]},
    {"id": "list_tables", "name": "列出数据表", "desc": "列出9006系统所有可查询的数据表", "icon": "📋", "tag": "只读查询", "danger": 0, "category": "经营",
     "method": "POST", "path": "/tools/query_ontology_tables",
     "params_schema": []},
    {"id": "get_table_schema", "name": "获取表结构", "desc": "获取指定表的所有列名及示例值", "icon": "🧱", "tag": "只读查询", "danger": 0, "category": "经营",
     "method": "POST", "path": "/tools/get_table_schema",
     "params_schema": [
         {"name": "table_name", "type": "string", "required": True, "desc": "表名，来自 list_tables"},
     ]},
    {"id": "query_table", "name": "查询明细", "desc": "查询原始明细（列投影/关键词/时间范围过滤）", "icon": "🔍", "tag": "只读查询", "danger": 0, "category": "经营",
     "method": "POST", "path": "/tools/query_ontology",
     "params_schema": [
         {"name": "table_name", "type": "string", "required": True, "desc": "表名"},
         {"name": "keyword", "type": "string", "required": False, "desc": "关键词"},
         {"name": "limit", "type": "integer", "required": False, "desc": "返回条数上限"},
     ]},
    {"id": "get_metrics", "name": "查询指标宽表", "desc": "查询ETL预计算指标宽表", "icon": "📈", "tag": "只读查询", "danger": 0, "category": "经营",
     "method": "POST", "path": "/tools/get_etl_metrics",
     "params_schema": [
         {"name": "job_key", "type": "string", "required": False, "desc": "ETL任务标识"},
         {"name": "dim_type", "type": "string", "required": False, "desc": "维度类型"},
     ]},
    # 研发类（9006 代码）
    {"id": "list_project_files", "name": "列出项目文件", "desc": "列出9006项目代码文件（backend/frontend/docs）", "icon": "📁", "tag": "只读查询", "danger": 0, "category": "研发",
     "method": "POST", "path": "/tools/list_project_files",
     "params_schema": []},
    {"id": "read_code_file", "name": "读取代码文件", "desc": "读取9006项目指定文件内容，支持分页", "icon": "📄", "tag": "只读查询", "danger": 0, "category": "研发",
     "method": "POST", "path": "/tools/read_code_file",
     "params_schema": [
         {"name": "file_path", "type": "string", "required": True, "desc": "相对项目根的文件路径，如 backend/main.py"},
     ]},
    {"id": "edit_code_file", "name": "编辑代码文件", "desc": "对9006文件做局部替换修改（支持模糊匹配），改前自动备份", "icon": "✏️", "tag": "高危写入", "danger": 1, "category": "研发",
     "method": "POST", "path": "/tools/edit_code_file",
     "params_schema": [
         {"name": "file_path", "type": "string", "required": True, "desc": "文件路径"},
         {"name": "old_text", "type": "string", "required": True, "desc": "被替换的旧内容"},
         {"name": "new_text", "type": "string", "required": True, "desc": "新内容"},
     ]},
    {"id": "search_code", "name": "搜索代码", "desc": "按关键词搜索9006项目代码，定位相关逻辑", "icon": "🔍", "tag": "只读查询", "danger": 0, "category": "研发",
     "method": "POST", "path": "/tools/search_code",
     "params_schema": [
         {"name": "keyword", "type": "string", "required": True, "desc": "搜索关键词"},
     ]},
    {"id": "write_new_file", "name": "新建文件", "desc": "在9006项目内新建文件（仅文件不存在时）", "icon": "📝", "tag": "高危写入", "danger": 1, "category": "研发",
     "method": "POST", "path": "/tools/write_new_file",
     "params_schema": [
         {"name": "file_path", "type": "string", "required": True, "desc": "文件路径"},
         {"name": "content", "type": "string", "required": True, "desc": "文件内容"},
     ]},
    {"id": "run_shell", "name": "执行验证命令", "desc": "执行白名单只读命令（git/pytest/ls），验证代码改动", "icon": "⚙️", "tag": "只读查询", "danger": 0, "category": "研发",
     "method": "POST", "path": "/tools/run_shell",
     "params_schema": [
         {"name": "command", "type": "string", "required": True, "desc": "白名单只读命令"},
     ]},
    # 项目管理域（两单一物/四算/工时/成本/集团指标，全部只读研判）
    {"id": "pm_project_read", "name": "项目四算与里程碑", "desc": "查询项目基础信息、里程碑进度与四算数据（概算/预算/核算/决算）", "icon": "📐", "tag": "只读查询", "danger": 0, "category": "项目管理",
     "method": "POST", "path": "/tools/pm_project_read",
     "params_schema": [
         {"name": "project_id", "type": "string", "required": False, "desc": "项目ID，为空返回全部项目概览"},
     ]},
    {"id": "pm_task_read", "name": "两单一物工单任务", "desc": "查询两单一物工单、任务明细与状态", "icon": "📋", "tag": "只读查询", "danger": 0, "category": "项目管理",
     "method": "POST", "path": "/tools/pm_task_read",
     "params_schema": [
         {"name": "project_id", "type": "string", "required": False, "desc": "项目ID，为空返回全部任务"},
         {"name": "status", "type": "string", "required": False, "desc": "任务状态：pending/running/done/overdue"},
     ]},
    {"id": "pm_workhour_read", "name": "日报工时明细", "desc": "查询日报、工时明细与人员填报数据（合规质检用）", "icon": "🕐", "tag": "只读查询", "danger": 0, "category": "项目管理",
     "method": "POST", "path": "/tools/pm_workhour_read",
     "params_schema": [
         {"name": "project_id", "type": "string", "required": False, "desc": "项目ID，为空返回全部"},
         {"name": "date", "type": "string", "required": False, "desc": "填报日期 YYYY-MM-DD"},
     ]},
    {"id": "pm_cost_calc", "name": "人力成本折算", "desc": "按日报工时折算项目人力成本与成本明细", "icon": "💰", "tag": "只读查询", "danger": 0, "category": "项目管理",
     "method": "POST", "path": "/tools/pm_cost_calc",
     "params_schema": [
         {"name": "project_id", "type": "string", "required": False, "desc": "项目ID，为空返回全部项目成本"},
     ]},
    {"id": "biz_metric_read", "name": "经营集团指标", "desc": "读取预计算经营&项目集团指标（人均效/元效/双按完成率/四算偏差）", "icon": "📊", "tag": "只读查询", "danger": 0, "category": "项目管理",
     "method": "POST", "path": "/tools/biz_metric_read",
     "params_schema": [
         {"name": "metric_name", "type": "string", "required": False, "desc": "指标名：人均效/元效/双按完成率/按期完成率/按预算完成率"},
         {"name": "period", "type": "string", "required": False, "desc": "周期：month/quarter/year"},
     ]},
    # 售前投标域（知识库/模板/导出，全部只读）
    {"id": "kb_knowledge_read", "name": "知识库检索", "desc": "检索内部知识库、历史方案、中标库", "icon": "📚", "tag": "只读查询", "danger": 0, "category": "售前投标",
     "method": "POST", "path": "/tools/kb_knowledge_read",
     "params_schema": [
         {"name": "keyword", "type": "string", "required": True, "desc": "检索关键词"},
         {"name": "limit", "type": "integer", "required": False, "desc": "返回条数上限"},
     ]},
    {"id": "bid_template_read", "name": "投标模板库", "desc": "读取投标标准模板库与技术规范模板", "icon": "📑", "tag": "只读查询", "danger": 0, "category": "售前投标",
     "method": "POST", "path": "/tools/bid_template_read",
     "params_schema": [
         {"name": "template_type", "type": "string", "required": False, "desc": "模板类型：tech_proposal/response/ppt_outline/impl_plan"},
     ]},
    {"id": "doc_export", "name": "文档结构化导出", "desc": "生成结构化投标文档（Word/PPT大纲），供人工下载", "icon": "📤", "tag": "只读查询", "danger": 0, "category": "售前投标",
     "method": "POST", "path": "/tools/doc_export",
     "params_schema": [
         {"name": "doc_type", "type": "string", "required": True, "desc": "文档类型：tech_proposal/response/ppt_outline/impl_plan"},
         {"name": "title", "type": "string", "required": False, "desc": "文档标题"},
     ]},

    # =====================================================================
    # 通讯类 - 邮件（独立MCP Tools，可被任意 Skill 复用）
    # =====================================================================
    {"id": "send_mail", "name": "邮件单发", "icon": "📧", "tag": "外呼写入", "danger": 1, "category": "通讯",
     "desc": "发送单封邮件（支持 TO + 抄送 CC + 回复线程 Message-ID，用于采购确认/验收通知等单发场景）",
     "method": "POST", "path": "/local/tools/send_mail", "server_id": "neuops-local", "group": "通讯-邮件",
     "params_schema": [
         {"name": "to", "type": "array[string]", "required": True, "desc": "收件人邮箱列表（如 [\"a@x.com\"]）"},
         {"name": "subject", "type": "string", "required": True, "desc": "邮件主题"},
         {"name": "body_text", "type": "string", "required": True, "desc": "邮件正文纯文本/HTML"},
         {"name": "cc", "type": "array[string]", "required": False, "desc": "抄送邮箱列表（全局邮件抄送由调用方注入）"},
         {"name": "reply_to_message_id", "type": "string", "required": False, "desc": "回复到某封邮件的 Message-ID（形成邮件线程）"},
     ]},
    {"id": "batch_send_mail", "name": "邮件批量发送", "icon": "📬", "tag": "外呼写入", "danger": 1, "category": "通讯",
     "desc": "批量发送邮件（每个收件人 1 封，统一主题+正文+统一抄送），用于询价群发",
     "method": "POST", "path": "/local/tools/batch_send_mail", "server_id": "neuops-local", "group": "通讯-邮件",
     "params_schema": [
         {"name": "receiver_email_list", "type": "array[string]", "required": True, "desc": "收件人邮箱列表"},
         {"name": "subject", "type": "string", "required": True, "desc": "统一邮件主题"},
         {"name": "body_text", "type": "string", "required": True, "desc": "统一邮件正文"},
         {"name": "cc", "type": "array[string]", "required": False, "desc": "每封邮件统一抄送邮箱列表"},
     ]},
    {"id": "read_inbox_mail", "name": "读取收件箱邮件", "icon": "📥", "tag": "只读查询", "danger": 0, "category": "通讯",
     "desc": "按时间窗口+指定发件人过滤，读取收件箱 IMAP 邮件，返回 message_id/发件人/正文文本/附件摘要",
     "method": "POST", "path": "/local/tools/read_inbox_mail", "server_id": "neuops-local", "group": "通讯-邮件",
     "params_schema": [
         {"name": "since_timestamp", "type": "integer", "required": True, "desc": "Unix 秒级时间戳，只读取这之后收到的邮件"},
         {"name": "filter_sender_email_list", "type": "array[string]", "required": False, "desc": "发件人白名单；为空则返回全部"},
     ]},

    # =====================================================================
    # 通讯类 - 飞书（独立MCP Tools，可被任意 Skill 复用）
    # =====================================================================
    {"id": "send_feishu_message", "name": "飞书消息推送", "icon": "💬", "tag": "外呼写入", "danger": 1, "category": "通讯",
     "desc": "给指定飞书用户发一条纯文本消息（支持 is_alert 加急），用于任务进度通知/告警",
     "method": "POST", "path": "/local/tools/send_feishu_message", "server_id": "neuops-local", "group": "通讯-飞书",
     "params_schema": [
         {"name": "receiver_feishu_open_id", "type": "string", "required": True, "desc": "飞书 Open ID（ou_xxx）"},
         {"name": "content", "type": "string", "required": True, "desc": "消息正文（支持飞书 markdown）"},
         {"name": "is_alert", "type": "boolean", "required": False, "desc": "是否加急推送（默认 false）"},
     ]},
    {"id": "send_feishu_card", "name": "飞书卡片推送", "icon": "🎴", "tag": "外呼写入", "danger": 1, "category": "通讯",
     "desc": "给指定飞书用户发交互卡片（schema 2.0 格式），用于报价确认/审批/发货通知等交互场景",
     "method": "POST", "path": "/local/tools/send_feishu_card", "server_id": "neuops-local", "group": "通讯-飞书",
     "params_schema": [
         {"name": "receiver_feishu_open_id", "type": "string", "required": True, "desc": "飞书 Open ID（ou_xxx）"},
         {"name": "card", "type": "object", "required": True, "desc": "飞书卡片 JSON（符合 schema 2.0，会自动包 raw 层）"},
     ]},

    # =====================================================================
    # 数据操作类 - 表 CRUD（独立MCP Tools，可被任意 Skill 复用）
    # =====================================================================
    {"id": "table_query", "name": "表查询", "icon": "🔍", "tag": "只读查询", "danger": 0, "category": "数据",
     "desc": "按条件查询业务表（采购任务/台账/供应商/合同/项目主数据等），支持 where 过滤+limit+排序+关键字模糊搜索",
     "method": "POST", "path": "/local/tools/table_query", "server_id": "neuops-local", "group": "数据-表操作",
     "params_schema": [
         {"name": "table_key", "type": "string", "required": True, "desc": "业务表标识，如 procurement_task/procurement_ledger/procurement_contract/procurement_spare_part"},
         {"name": "filters", "type": "object", "required": False, "desc": "{字段: 值} 精确匹配过滤，如 {\"contract_no\": \"IDZB..\"}"},
         {"name": "keyword", "type": "string", "required": False, "desc": "关键字模糊搜索（对表中所有TEXT列做LIKE匹配，如 keyword='内存'）"},
         {"name": "keyword_fields", "type": "array", "required": False, "desc": "指定搜索列（可选，不传则自动搜索所有TEXT列）"},
         {"name": "limit", "type": "integer", "required": False, "desc": "返回条数上限（默认 100）"},
     ]},
    {"id": "table_insert", "name": "表插入", "icon": "➕", "tag": "高危写入", "danger": 1, "category": "数据",
     "desc": "向业务表插入一条记录（自动写 created_at），返回新 id",
     "method": "POST", "path": "/local/tools/table_insert", "server_id": "neuops-local", "group": "数据-表操作",
     "params_schema": [
         {"name": "table_key", "type": "string", "required": True, "desc": "业务表标识"},
         {"name": "record_id", "type": "string", "required": False, "desc": "主键 ID（不填则自动生成）"},
         {"name": "data", "type": "object", "required": True, "desc": "要插入的 {字段: 值}"},
     ]},
    {"id": "table_update", "name": "表更新", "icon": "✏️", "tag": "高危写入", "danger": 1, "category": "数据",
     "desc": "按主键 ID 更新业务表记录（自动更新 updated_at）",
     "method": "POST", "path": "/local/tools/table_update", "server_id": "neuops-local", "group": "数据-表操作",
     "params_schema": [
         {"name": "table_key", "type": "string", "required": True, "desc": "业务表标识"},
         {"name": "record_id", "type": "string", "required": True, "desc": "主键 ID"},
         {"name": "data", "type": "object", "required": True, "desc": "要更新的 {字段: 值}"},
     ]},
    {"id": "table_upsert", "name": "表幂等插入或更新", "icon": "🔁", "tag": "高危写入", "danger": 1, "category": "数据",
     "desc": "主键存在则更新，不存在则插入（表级幂等），用于定时 tick 不重复写数据",
     "method": "POST", "path": "/local/tools/table_upsert", "server_id": "neuops-local", "group": "数据-表操作",
     "params_schema": [
         {"name": "table_key", "type": "string", "required": True, "desc": "业务表标识"},
         {"name": "record_id", "type": "string", "required": True, "desc": "主键 ID"},
         {"name": "data", "type": "object", "required": True, "desc": "要写入/更新的 {字段: 值}"},
     ]},

    # =====================================================================
    # 业务解析类 - 采购询比价（独立MCP Tools，可被其他采购类 Skill 复用）
    # =====================================================================
    {"id": "procurement_parse_quote", "name": "供应商报价邮件解析", "icon": "💴", "tag": "只读查询", "danger": 0, "category": "解析",
     "desc": "6 层加固解析供应商报价邮件正文：兼容\"只回一个数字\"、带¥3200元、乘法式(3×3200=9600)、漏关键字等场景，返回单价/总价/品牌/型号/货期 + 解析策略标记",
     "method": "POST", "path": "/local/tools/procurement_parse_quote", "server_id": "neuops-local", "group": "业务解析-采购",
     "params_schema": [
         {"name": "body", "type": "string", "required": True, "desc": "邮件原文正文"},
         {"name": "expected_qty", "type": "integer", "required": False, "desc": "预期采购数量（用于反推单/总价）"},
         {"name": "spare_part_model", "type": "string", "required": False, "desc": "备件型号（没有解析到型号时的默认值）"},
     ]},
    {"id": "procurement_parse_logistics", "name": "供应商发货邮件解析", "icon": "📦", "tag": "只读查询", "danger": 0, "category": "解析",
     "desc": "3 层加固解析供应商发货邮件：兼容\"顺丰 123456\"、\"单号 SF123\"、\"SF1234567890\"、13 位纯数字民营单号等；返回单号/载体/发货日期/原文片段",
     "method": "POST", "path": "/local/tools/procurement_parse_logistics", "server_id": "neuops-local", "group": "业务解析-采购",
     "params_schema": [
         {"name": "body", "type": "string", "required": True, "desc": "邮件原文正文"},
     ]},

    # =====================================================================
    # 采购业务动作类（智能体对话入口，走 9006 标准流程，保证数据一致+自动触发Flow）
    # =====================================================================
    {"id": "procurement_create_task", "name": "创建询比价采购任务", "icon": "📝", "tag": "业务写入", "danger": 1, "category": "采购",
     "desc": "【对话入口专用】创建询比价采购任务。自动生成task_id、计算deadline、写操作日志、触发询价邮件+飞书通知。重要：project_id/project_name/inquiry_supplier_list 全部可选，对话中绝对不要向用户追问这3个参数！",
     "method": "POST", "path": "/local/tools/procurement_create_task", "server_id": "neuops-local", "group": "业务动作-采购",
     "params_schema": [
         {"name": "project_id", "type": "string", "required": False, "desc": "⚠️ 不要向用户追问此项！传空字符串即可。"},
         {"name": "project_name", "type": "string", "required": False, "desc": "⚠️ 不要向用户追问此项！传空字符串即可。"},
         {"name": "contract_no", "type": "string", "required": False, "desc": "合同编号。用户主动提到合同时才追问，否则传空字符串。"},
         {"name": "spare_part_model", "type": "string", "required": True, "desc": "备件型号（必填，如 'DDR4 32GB 3200MHz'）"},
         {"name": "purchase_qty", "type": "number", "required": True, "desc": "采购数量（必填，正整数或小数）"},
         {"name": "emergency_level", "type": "string", "required": True, "desc": "紧急等级（必填，枚举：2h / 4h / 5h）"},
         {"name": "inquiry_supplier_list", "type": "array", "required": False,
          "desc": "⚠️ 不要向用户追问此项！不传时系统自动带全量资源池3家。仅当用户主动要求追加临时供应商时才传 [{name,email}]。"},
         {"name": "creator", "type": "string", "required": False, "desc": "创建人，默认 agent"},
     ]},

    # =====================================================================
    # 采购对话辅助查询类（skill-proc-chat 专用，LLM 对话式收集信息时调用，列出选项给用户选）
    # =====================================================================
    {"id": "procurement_query_contract", "name": "查询可用合同", "icon": "📋", "tag": "只读查询", "danger": 0, "category": "采购-对话辅助",
     "desc": "查询可用合同列表（用于对话中给用户列出选项）。支持 keyword 关键字模糊匹配合同编号/名称，返回 id/contract_no/contract_name/pm_name/pm_email。",
     "method": "POST", "path": "/local/tools/procurement_query_contract", "server_id": "neuops-local", "group": "对话辅助-采购",
     "params_schema": [
         {"name": "keyword", "type": "string", "required": False, "desc": "合同编号或名称关键字（模糊匹配，可空=返回全部）"},
     ]},
    {"id": "procurement_query_spare_part", "name": "查询备件型号", "icon": "🔧", "tag": "只读查询", "danger": 0, "category": "采购-对话辅助",
     "desc": "查询可用备件型号列表（用于对话中给用户列出选项）。支持 keyword 关键字模糊匹配备件名称/型号/品牌/编码，返回 id/part_code/part_name/spec_model/brand/unit/category。",
     "method": "POST", "path": "/local/tools/procurement_query_spare_part", "server_id": "neuops-local", "group": "对话辅助-采购",
     "params_schema": [
         {"name": "keyword", "type": "string", "required": False, "desc": "备件名称/型号/品牌关键字（模糊匹配，可空=返回全部）"},
     ]},
    {"id": "procurement_query_supplier", "name": "查询资源池供应商", "icon": "🏢", "tag": "只读查询", "danger": 0, "category": "采购-对话辅助",
     "desc": "查询资源池供应商列表（用于对话中展示可选供应商/确认默认资源池内容）。支持 keyword 关键字模糊匹配供应商名称/邮箱，返回 id/name/email/capability。",
     "method": "POST", "path": "/local/tools/procurement_query_supplier", "server_id": "neuops-local", "group": "对话辅助-采购",
     "params_schema": [
         {"name": "keyword", "type": "string", "required": False, "desc": "供应商名称或邮箱关键字（模糊匹配，可空=返回全部）"},
     ]},

    # =====================================================================
    # 本体计算类（探索/溯源/模拟/预测等临时口径，直调共享 ontos 子模块，与 9006 固化显示同一份算法）
    # =====================================================================
    {"id": "ontology_compute", "name": "本体计算(临时口径)", "icon": "🧮", "tag": "只读计算", "danger": 0, "category": "本体",
     "desc": "直接调用本体 TBox 纯函数做回款周期/资金占用/毛利率/ROI/成本预警等计算（探索/模拟/预测等临时口径，不依赖 9006 固化报表）。结果属临时口径，非固化口径。",
     "method": "POST", "path": "/local/tools/ontology_compute", "server_id": "neuops-local", "group": "本体计算",
     "params_schema": [
         {"name": "function", "type": "string", "required": True,
          "desc": "计算函数名：payment_cycle / capital_occupation / project_margin / project_roi / cost_rollup / receivable_status / project_cost_warning（亦支持 F- 前缀）"},
         {"name": "params", "type": "object", "required": False,
          "desc": "参数字典，如 {'sign_date':'2024-01-01','receipts':[{'received_date':'2024-05-01'}],'basis':'first'}"},
     ]},
]


MCP_SERVER_SEED = [
    # 本地 MCP Server：9010 MCP 工具网关（见 mcp_gateway.py），承载运维/经营/研发/项目管理/售前投标全部 34 个工具
    {
        "id": "mcp-gateway",
        "name": "NeuOps MCP 工具网关",
        "desc": "统一 MCP 工具网关（/tools 工具发现端点），承载运维/经营/研发/项目管理/售前投标全部 34 个工具",
        "base_url": "http://122.51.98.98:9010",
        "type": "gateway",
        "auth": "",
        "status": "online",
        "last_sync": "",
    },
    # 本地 Python 工具集：承载邮件/飞书/表 CRUD/业务解析等本地 Python 实现的 MCP 工具（无需 MCP Server 网关转发）
    {
        "id": "neuops-local",
        "name": "NeuOps 本地 Python 工具集",
        "desc": "承载邮件发送/飞书消息/表 CRUD/业务解析等本地 Python 实现的 MCP 工具（直接调用本地函数，无需网关转发）",
        "base_url": "local://python",
        "type": "local",
        "auth": "",
        "status": "online",
        "last_sync": "",
    },
]


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
]


MOCK_LONG_TASKS = []


MOCK_TODOS = [
    # 待办均来自 9007 一体化监控平台真实告警（alerts 表）
    {"id": "todo-1", "type": "告警", "title": "neuops-agent 应用健康检查失败（degraded）", "level": "critical", "time": "2026-08-15 23:47", "source_id": "rule-ops-004", "auto_skill": "skill-2"},
    {"id": "todo-2", "type": "告警", "title": "contract-compare 应用健康检查失败（degraded）", "level": "critical", "time": "2026-08-15 10:22", "source_id": "rule-ops-004", "auto_skill": "skill-2"},
    {"id": "todo-3", "type": "告警", "title": "单会话 Token 超限（conv-1786688554336）", "level": "info", "time": "2026-08-14 14:51", "source_id": "rule-004", "auto_skill": "skill-1"},
    {"id": "todo-4", "type": "告警", "title": "智能体 emp-001 长期不活跃（999 天无调用）", "level": "warning", "time": "2026-08-14 14:51", "source_id": "rule-005", "auto_skill": "skill-1"},
    {"id": "todo-5", "type": "事件", "title": "告警详情页接入根因分析建议展示", "level": "info", "time": "2026-08-16 01:50", "source_id": "ALERT-OPS", "auto_skill": ""},
]


MOCK_TODO_HISTORY = [
    {"id": "h-1", "type": "告警", "title": "Token 用量突增（60分钟 217505）", "level": "warning", "time": "2026-08-14 14:51", "handled_time": "2026-08-14 20:02", "result": "已恢复：Token 用量回落至阈值内"},
    {"id": "h-2", "type": "事件", "title": "neuops-agent 健康检查失败恢复（ALERT-OPS-20260816）", "level": "critical", "time": "2026-08-16 00:43", "handled_time": "2026-08-16 00:43", "result": "已恢复：人工重启服务后恢复"},
    {"id": "h-4", "type": "巡检", "title": "全域巡检：服务器/数据库/网络实体指标采集", "level": "normal", "time": "2026-08-16 00:00", "handled_time": "2026-08-16 00:05", "result": "已完成：19 个实体 74846 条指标采集正常"},
    {"id": "h-5", "type": "任务", "title": "ETL 指标预计算（gross-margin 签单毛利率）", "level": "normal", "time": "2026-08-16 00:00", "handled_time": "2026-08-16 00:02", "result": "已完成：经营指标宽表更新"},
]


MOCK_BG_TASKS = [
    {"id": "bgt-1", "name": "监控探针采集", "status": "running", "desc": "9007 实时采集服务器/数据库/网络实体指标与系统日志"},
    {"id": "bgt-2", "name": "告警收敛引擎", "status": "running", "desc": "持续监听告警流，去重聚合、抖动抑制，产出风险事件"},
    {"id": "bgt-3", "name": "ETL 指标预计算", "status": "running", "desc": "9006 定时计算签单毛利率等经营指标宽表"},
    {"id": "bgt-4", "name": "AI 自监控巡检", "status": "running", "desc": "9007 监控数字员工任务/调用/长任务，异常自动告警"},
    {"id": "bgt-5", "name": "代码变更回归检查", "status": "paused", "desc": "9006 代码变更后自动跑测试，失败升级人工处理"},
]


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
]


MCP_SERVER_SEED = [
    # 本地 MCP Server：9010 MCP 工具网关（见 mcp_gateway.py），承载运维/经营/研发/项目管理/售前投标全部 34 个工具
    {
        "id": "mcp-gateway",
        "name": "NeuOps MCP 工具网关",
        "desc": "统一 MCP 工具网关（/tools 工具发现端点），承载运维/经营/研发/项目管理/售前投标全部 34 个工具",
        "base_url": "http://127.0.0.1:9010",
        "type": "gateway",
        "auth": "",
        "status": "online",
        "last_sync": "",
    },
]


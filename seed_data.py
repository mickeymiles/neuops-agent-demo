# -*- coding: utf-8 -*-
"""
NeuOps Agent Demo 种子数据（预置内容）
首次启动时由 main.py 导入数据库；运行时 API 一律读库，不再读取本文件。
抽离目的：数据与代码分离，main.py 只保留业务逻辑。
"""

SKILLS = [
    {"id": "skill-1", "name": "服务故障根因分析", "desc": "自动采集指标、日志、变更记录，结合CMDB拓扑进行多维度根因定位，输出故障分析报告", "category": "official", "tags": ["故障分析","根因定位"], "enabled": True},
    {"id": "skill-2", "name": "告警关联变更排查", "desc": "将当前告警与近期变更工单自动关联分析，识别变更引入的异常，输出关联性结论", "category": "official", "tags": ["告警","变更"], "enabled": True},
    {"id": "skill-3", "name": "业务集群巡检报告生成", "desc": "按预设巡检项自动采集资源指标、告警信息、服务健康状态，生成结构化巡检报告", "category": "official", "tags": ["巡检","报告"], "enabled": True},
    {"id": "skill-4", "name": "资产拓扑依赖查询", "desc": "查询CMDB中指定应用的上下游依赖关系，生成依赖拓扑视图和服务影响范围分析", "category": "official", "tags": ["CMDB","拓扑"], "enabled": False},
    {"id": "skill-5", "name": "变更风险评估与执行", "desc": "对待执行变更进行影响面分析，评估上下游服务风险等级，输出变更风险评估报告并执行审批自动化作业", "category": "official", "tags": ["变更","风险"], "enabled": False},
    {"id": "skill-6", "name": "工单智能处置", "desc": "自动分析ITSM工单内容，匹配历史相似工单解决方案，调用MCP工具完成标准化处置流程", "category": "custom", "tags": ["工单","自动化"], "enabled": True},
    {"id": "skill-7", "name": "数据库慢查询诊断", "desc": "自动采集慢查询日志，分析SQL执行计划，识别索引缺失，输出优化建议", "category": "market", "tags": ["数据库","性能"], "enabled": False},
    {"id": "skill-8", "name": "容器资源画像分析", "desc": "采集K8s集群中Pod的资源使用趋势，识别资源浪费和瓶颈，输出优化建议", "category": "market", "tags": ["容器","K8s"], "enabled": False},
    {"id": "skill-9", "name": "安全漏洞扫描报告", "desc": "对指定服务进行CVE漏洞扫描，关联版本信息，输出安全风险评估报告", "category": "custom", "tags": ["安全","扫描"], "enabled": False},
    {"id": "skill-10", "name": "采购清单比对", "desc": "对接9006合同比对系统，查询比对进度、分析差异、识别高危异常，输出评审建议", "category": "custom", "tags": ["合同","采购","比对","9006"], "enabled": True},
    {"id": "skill-11", "name": "经营指标分析", "desc": "对接9006指标数据集MCP，查询签单毛利率、回款毛利率等定时ETL预计算指标，输出经营分析报告", "category": "custom", "tags": ["经营","指标","毛利率","9006"], "enabled": True},
    {"id": "skill-12", "name": "合同明细探查", "desc": "对接9006原子本体MCP，按合同编号/关键词查询原始合同、付款、收款明细，输出探查结果", "category": "custom", "tags": ["合同","明细","查询","9006"], "enabled": True},
    {"id": "skill-13", "name": "系统研发改造", "desc": "访问9006经营业务展示系统的代码（后端/前端文件），理解用户需求后直接修改系统代码实现功能调整", "category": "custom", "tags": ["研发","代码","9006"], "enabled": True},
]


MOCK_EMPLOYEES = [
    {"id": "emp-004", "name": "经营业务专家", "desc": "专注采购合同比对、经营指标分析、合同明细探查等经营业务场景。对接9006经营分析系统：通过原子本体MCP查询原始合同/付款/收款明细，通过指标数据集MCP查询签单毛利率等定时ETL预计算指标，通过合同比对引擎分析供应商报价差异。", "type": "经营分析", "created": "2026-08-11", "updated": "2026-08-13",
     "skills": ["skill-10","skill-11","skill-12"],
     "rag_kb": "经营知识库-合同案例", "prompt": "你是一位经营业务分析专家，负责经营分析和顾问工作。你通过9006经营分析系统的三类能力服务用户：①合同比对——用户在9006上传合同基准Excel和供应商报价Excel后，查询比对结果、分析差异、识别高危异常项；②指标分析——通过指标数据集MCP读取定时ETL预计算的签单毛利率、回款毛利率等指标宽表，做同比/环比解读，不做原始聚合计算；③明细探查——通过原子本体MCP按合同编号或关键词查询原始合同、付款、收款明细。指标口径以9006定时任务计算为准，你只做解读，不自行重算。", "model": "deepseek-v4"},
    {"id": "emp-005", "name": "研发专家", "desc": "开发类数字员工。访问9006经营业务展示系统的代码（后端backend/前端frontend），理解用户对系统功能的修改思路后，直接读取并修改9006系统的代码文件实现功能调整。", "type": "系统研发", "created": "2026-08-13", "updated": "2026-08-13",
     "skills": ["skill-13"],
     "rag_kb": "研发知识库-9006代码", "prompt": "你是一位研发专家，负责按用户需求修改9006经营业务展示系统的代码。你先列出项目文件了解结构，再读取相关文件理解现状，然后用edit_code_file做局部修改。修改前先说明你的改造思路和要改哪个文件、改什么；改动要克制，只改必要之处，不要重写整个文件。", "model": "deepseek-v4"},
]


MOCK_LONG_TASKS = []


MOCK_TODOS = [
    {"id": "todo-1", "type": "告警", "title": "订单服务延迟突增，待确认根因", "level": "high", "time": "2026-08-08 14:32", "source_id": "ALM-20260807-001", "auto_skill": "skill-2"},
    {"id": "todo-4", "type": "告警", "title": "支付服务错误率上升至5.2%", "level": "high", "time": "2026-08-08 13:05", "source_id": "ALM-20260808-007", "auto_skill": "skill-2"},
    {"id": "todo-2", "type": "工单", "title": "数据库慢查询故障（T20260808-003）", "level": "normal", "time": "2026-08-08 11:20", "source_id": "INC-20260808-003", "auto_skill": "skill-6"},
    {"id": "todo-5", "type": "工单", "title": "Redis连接异常（T20260808-009）", "level": "normal", "time": "2026-08-08 09:40", "source_id": "INC-20260808-009", "auto_skill": "skill-6"},
    {"id": "todo-3", "type": "变更", "title": "订单实例滚动重启，等待审批", "level": "high", "time": "2026-08-08 10:45", "source_id": "CHG-20260808-005", "auto_skill": "skill-5"},
    {"id": "todo-6", "type": "变更", "title": "数据库连接池参数调整，等待审批", "level": "normal", "time": "2026-08-08 08:30", "source_id": "CHG-20260808-006", "auto_skill": "skill-5"},
]


MOCK_TODO_HISTORY = [
    {"id": "h-1", "type": "告警", "title": "数据库连接数接近上限告警", "level": "high", "time": "2026-08-07 18:20", "handled_time": "2026-08-07 18:45", "result": "已处理：重启实例恢复连接"},
    {"id": "h-2", "type": "工单", "title": "订单服务磁盘空间不足（T20260807-012）", "level": "normal", "time": "2026-08-07 15:10", "handled_time": "2026-08-07 16:00", "result": "已处理：清理历史日志释放空间"},
    {"id": "h-3", "type": "变更", "title": "支付服务配置灰度发布", "level": "high", "time": "2026-08-07 11:00", "handled_time": "2026-08-07 11:30", "result": "已审批通过并执行完成"},
    {"id": "h-4", "type": "告警", "title": "订单服务CPU使用率过高", "level": "normal", "time": "2026-08-06 20:15", "handled_time": "2026-08-06 20:40", "result": "已处理：扩容实例分散负载"},
    {"id": "h-5", "type": "工单", "title": "支付网关证书即将过期（T20260806-021）", "level": "high", "time": "2026-08-06 14:00", "handled_time": "2026-08-06 15:00", "result": "已处理：更新SSL证书"},
]


MOCK_BG_TASKS = [
    {"id": "bgt-1", "name": "告警实时收敛", "status": "running", "desc": "持续监听告警流，收敛重复告警，降噪后产出风险事件"},
    {"id": "bgt-2", "name": "支付集群定时巡检", "status": "running", "desc": "每日 08:00 / 20:00 自动执行巡检，生成报告推送"},
    {"id": "bgt-3", "name": "数据库慢查询监控", "status": "paused", "desc": "实时采集慢查询日志，超过阈值自动生成工单"},
]


SKILL_DETAILS = {
    "skill-1": {
        "type": "Workflow业务编排技能",
        "prompt": "你是运维故障分析专家，需要完成服务故障根因排查。\n1、调用相关MCP工具，采集业务指标、异常日志、资产拓扑、变更工单；\n2、综合全部信息定位故障根因；\n3、输出风险评估、处置建议；\n4、涉及变更操作必须输出审批按钮标记，等待人工确认后执行。",
        "tools": ["get_business_metric", "search_service_log", "query_cmdb_topology", "query_change_record"],
        "flow": "执行流程：\n1、接收用户输入的故障分析范围参数\n2、并行调用：查询业务指标 + 检索异常日志\n3、串行调用：查询资产拓扑 → 查询近期变更记录\n4、大模型汇总全部工具返回数据，做根因推理\n5、输出结构化故障分析结论与处置建议\n6、如果识别需要变更自愈操作，输出高危操作按钮，等待人工审批确认",
    },
    "skill-2": {
        "type": "Workflow业务编排技能",
        "prompt": "你是变更影响分析专家，负责排查告警与变更的关联关系。\n1、获取当前时间窗口内的所有活跃告警；\n2、拉取告警发生前24小时内的变更工单；\n3、按时间线对齐告警与变更，逐项分析因果关系；\n4、输出关联性结论（强关联/弱关联/无关），标注置信度。",
        "tools": ["query_alarm_info", "query_change_record", "query_cmdb_topology"],
        "flow": "执行流程：\n1、接收用户输入的告警ID或时间范围参数\n2、并行调用：查询告警详情 + 查询变更记录\n3、按时间线将告警与变更工单对齐\n4、调用CMDB拓扑，分析变更影响链路上的告警传播路径\n5、大模型综合判定关联关系，输出置信度评分\n6、输出告警-变更关联分析报告与建议",
    },
    "skill-3": {
        "type": "Workflow业务编排技能",
        "prompt": "你是运维巡检专家，需要按预设巡检项生成业务集群巡检报告。\n1、采集目标集群所有服务的资源指标（CPU/内存/QPS/延迟）；\n2、拉取最近24小时告警信息；\n3、检查各服务健康检查端点状态；\n4、汇总生成结构化巡检报告，标注异常项和建议。",
        "tools": ["get_business_metric", "query_alarm_info", "search_service_log"],
        "flow": "执行流程：\n1、接收巡检目标集群范围参数\n2、并行采集：全集群业务指标 + 告警信息 + 异常日志\n3、逐服务评估健康状态（正常/警告/异常）\n4、汇总生成结构化 Markdown 巡检报告\n5、标注需关注的异常项并给出处理建议",
    },
    "skill-4": {
        "type": "Workflow业务编排技能",
        "prompt": "你是CMDB资产分析专家，需要分析指定应用的依赖关系和影响范围。\n1、查询目标应用在CMDB中的资产信息；\n2、展开上下游依赖链路（递归2层）；\n3、标注关键依赖节点（数据库、缓存、消息队列）；\n4、输出依赖拓扑视图和变更影响范围分析。",
        "tools": ["query_cmdb_topology", "get_business_metric"],
        "flow": "执行流程：\n1、接收目标应用名称或应用ID\n2、查询CMDB获取目标应用基础资产信息\n3、向上递归查询依赖方（谁依赖我），向下查询被依赖方（我依赖谁）\n4、标注关键中间件节点（DB/Cache/MQ）\n5、结合业务指标展示各节点实时负载\n6、输出依赖拓扑报告 + 变更影响范围矩阵",
    },
    "skill-5": {
        "type": "Workflow业务编排技能",
        "prompt": "你是变更风险管控与执行专家，需要完成变更风险预评估和审批执行。\n1、获取待变更目标资产的CMDB拓扑信息；\n2、分析变更影响的上下游服务范围；\n3、检查受影响服务的当前健康状态和告警；\n4、输出风险评估等级（低/中/高/严重）及建议窗口期；\n5、如评估通过，自动执行变更操作并验证；\n6、涉及高危变更必须输出审批按钮标记，等待人工确认后执行。",
        "tools": ["query_change_risk", "query_cmdb_topology", "query_alarm_info", "run_auto_job", "verify_service_status"],
        "flow": "执行流程：\n1、接收待变更目标信息（应用名/资源ID + 变更内容描述）\n2、查询CMDB获取变更目标及其上下游拓扑\n3、并行检查：受影响服务的当前告警 + 健康状态\n4、综合评估风险等级，标注关键风险点\n5、输出风险评估报告（含影响矩阵 + 建议窗口期）\n6、如识别为高风险变更，标记需走审批流程，等待人工确认后执行自动化作业\n7、变更完成后自动验证服务健康状态",
    },
    "skill-6": {
        "type": "Workflow业务编排技能",
        "prompt": "你是ITSM工单处置专家，需要自动化处理运维工单。\n1、解析工单内容，提取关键信息（故障现象、影响范围、紧急程度）；\n2、检索历史相似工单及其处置方案；\n3、匹配对应MCP原子工具执行标准化处置；\n4、处置完成后验证服务恢复状态；\n5、输出处置记录，自动关闭工单。",
        "tools": ["query_change_record", "search_service_log", "get_business_metric", "verify_service_status"],
        "flow": "执行流程：\n1、接收工单ID，解析工单内容和紧急程度\n2、检索历史相似工单处理记录\n3、根据工单类型自动匹配处置Skill\n4、调用MCP工具执行标准化处置操作\n5、处置完成后验证服务恢复\n6、生成处置记录并自动关闭工单",
    },
    "skill-10": {
        "type": "Workflow业务编排技能",
        "prompt": "你是经营业务分析专家，负责采购合同与供应商报价比对的分析和顾问工作。\n1、用户日常在9006合同比对系统（http://122.51.98.98:9006）上传合同基准和供应商报价，执行逐项比对；\n2、你的职责是：查询9006已有比对结果 → 分析差异情况 → 识别高危异常 → 给出整改建议；\n3、当用户提及具体合同名称时，自动从9006拉取真实比对数据；\n4、比对引擎能力：50+别名兜底匹配、单位归一化、三层匹配算法（子串/数字+单位/中文模糊70%）；\n5、输出结构化比对报告，标注差异风险等级（高/中/低），给出可执行的整改建议。",
        "tools": ["query_contracts", "get_comparison_results", "get_contract_stats", "export_report"],
        "flow": "执行流程：\n1、用户在9006系统（http://122.51.98.98:9006）上传合同基准和供应商报价，执行比对\n2、用户通过对话向经营业务专家发起查询：「LS的比对结果」「GYYD缺了多少项」\n3、专家调用9006 API：GET /api/contracts 定位合同 → GET /api/contract/{id}/compare/results 拉取真实结果\n4、汇总比对数据：完全匹配/匹配异常/待采购/供应商增项四类统计\n5、重点分析差异项：规格不一致、数量偏离、供应商未报价，标注风险等级\n6、输出结构化比对报告 + 评审建议 + 跳转9006查看完整明细的链接",
    },
    "skill-7": {
        "type": "Workflow业务编排技能",
        "prompt": "你是数据库性能分析专家，负责诊断数据库慢查询问题。\n1、采集慢查询日志，按执行时长、频次排序定位TOP慢SQL；\n2、分析SQL执行计划，识别缺失索引、全表扫描等问题；\n3、关联业务指标判断慢查询对服务的影响；\n4、输出慢查询诊断报告与SQL优化建议。",
        "tools": ["search_slow_query", "get_business_metric"],
        "flow": "执行流程：\n1、接收数据库实例名和时间范围\n2、检索慢查询日志，统计TOP慢SQL\n3、查询相关服务业务指标，评估影响\n4、分析执行计划与索引情况\n5、输出慢查询诊断报告与优化建议",
    },
    "skill-8": {
        "type": "Workflow业务编排技能",
        "prompt": "你是容器资源分析专家，负责分析K8s集群资源使用情况。\n1、采集各Pod的CPU、内存使用趋势；\n2、识别资源浪费（长期低负载）与资源瓶颈（频繁触顶）；\n3、关联服务健康状态评估资源问题影响；\n4、输出资源画像报告与优化建议（扩缩容、限流等）。",
        "tools": ["query_container_resource", "get_business_metric"],
        "flow": "执行流程：\n1、接收集群名称和命名空间\n2、采集Pod资源使用趋势\n3、识别资源浪费与瓶颈\n4、关联服务健康状态\n5、输出资源画像报告与优化建议",
    },
    "skill-9": {
        "type": "Workflow业务编排技能",
        "prompt": "你是安全漏洞分析专家，负责对服务进行漏洞扫描与风险评估。\n1、获取目标服务的版本信息与依赖清单；\n2、执行CVE漏洞扫描，匹配已知漏洞库；\n3、按严重程度（严重/高/中/低）分类统计漏洞；\n4、输出安全风险评估报告与修复建议。",
        "tools": ["scan_vulnerability", "query_cmdb_topology"],
        "flow": "执行流程：\n1、接收目标服务名称\n2、获取服务版本与依赖信息\n3、执行CVE漏洞扫描\n4、按严重程度分类统计\n5、输出安全风险评估报告与修复建议",
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
        "prompt": "你是研发专家，负责按用户需求修改9006经营业务展示系统的代码。\n1、列出项目文件了解结构；\n2、用search_code按关键词搜索定位相关逻辑；\n3、读取相关文件理解现状；\n4、用edit_code_file做局部修改（支持模糊匹配，改前自动备份），新建文件用write_new_file；\n5、用run_shell验证改动（git diff / pytest）；\n6、改动要克制，只改必要之处，不重写整个文件。",
        "tools": ["list_project_files", "search_code", "read_code_file", "write_new_file", "edit_code_file", "run_shell"],
        "flow": "执行流程：\n1、列出9006项目代码文件\n2、搜索定位相关逻辑所在文件\n3、读取相关文件理解现状\n4、说明改造思路后执行局部修改或新建文件\n5、跑测试/看diff验证改动结果",
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
    # ── 运维相关会话 ──
    "conv-001": {
        "title": "订单服务延迟排查",
        "employee_id": "emp-001",
        "messages": [
            {"role": "user", "content": "订单服务最近延迟持续上涨，完成全链路排查，分析潜在根因"},
            {"role": "agent", "thought": "任务分解：\n1. 用户反馈订单服务延迟持续上涨\n2. 匹配可用Skill：服务故障根因分析Skill（skill-1）\n3. 执行流程：采集指标 → 检索日志 → 查询拓扑 → 分析变更",
             "tools": [
                 {"tool": "get_business_metric", "service": "order-service"},
                 {"tool": "search_service_log", "service": "order-service", "level": "ERROR"},
                 {"tool": "query_cmdb_topology", "app": "order-service"},
                 {"tool": "query_change_record", "service": "order-service"},
             ],
             "conclusion": """## 🔍 故障根因分析

**根因**：数据库连接池耗尽，max_connections从200调整为150导致。

**建议**：恢复连接池配置至200，或增加应用实例数分散连接负载。"""},
        ]
    },
    "conv-002": {
        "title": "支付服务告警分析",
        "employee_id": "emp-001",
        "messages": [
            {"role": "user", "content": "支付服务错误率上升，分析告警原因"},
            {"role": "agent", "thought": "任务分解：\n1. 支付服务错误率上升至5.2%\n2. 关联Redis连接异常\n3. 需检查Redis集群健康状态",
             "tools": [
                 {"tool": "query_alarm_info", "service": "payment-service"},
                 {"tool": "get_business_metric", "service": "payment-service"},
             ],
             "conclusion": """## 🚨 支付服务告警分析

**根因**：Redis集群节点失联导致缓存不可用，支付请求直接穿透到数据库。

**建议**：重启故障Redis节点，配置哨兵自动故障转移。"""},
        ]
    },
    "conv-003": {
        "title": "数据库连接池问题",
        "employee_id": "emp-001",
        "messages": [
            {"role": "user", "content": "数据库连接池频繁告警，排查根本原因"},
            {"role": "agent", "thought": "任务分解：\n1. 数据库连接数接近上限\n2. 慢查询增加连接占用时间\n3. 需优化SQL和连接池配置",
             "tools": [
                 {"tool": "search_service_log", "service": "order-service", "level": "WARN"},
                 {"tool": "run_auto_job", "job_type": "配置调整", "target": "db连接池"},
             ],
             "conclusion": """## 🔧 数据库连接池优化

| 参数 | 原值 | 建议值 |
|------|------|--------|
| max_connections | 150 | 200 |
| wait_timeout | 30s | 15s |

已提交变更审批，确认后自动执行。"""},
        ]
    },
}


MCP_TOOL_SEED = [
    # 运维类（mcp-gateway 9010 直连）
    {"id": "get_business_metric", "name": "查询业务历史指标", "desc": "获取服务QPS、响应延迟、错误率时序指标", "icon": "📊", "tag": "只读查询", "danger": 0, "category": "运维",
     "method": "POST", "path": "/tools/get_business_metric",
     "params_schema": [
         {"name": "service", "type": "string", "required": False, "desc": "服务名，如 order-service"},
         {"name": "metric", "type": "string", "required": False, "desc": "指标名，all/latency_p99/error_rate/qps"},
     ]},
    {"id": "search_service_log", "name": "检索异常日志", "desc": "按服务、时间范围检索应用错误日志堆栈", "icon": "📜", "tag": "只读查询", "danger": 0, "category": "运维",
     "method": "POST", "path": "/tools/search_service_log",
     "params_schema": [
         {"name": "service", "type": "string", "required": False, "desc": "服务名"},
         {"name": "level", "type": "string", "required": False, "desc": "日志级别，ERROR/ALL"},
         {"name": "limit", "type": "integer", "required": False, "desc": "返回条数上限"},
     ]},
    {"id": "query_cmdb_topology", "name": "查询CMDB资产拓扑", "desc": "查询应用上下游依赖资产实例信息", "icon": "🔗", "tag": "只读查询", "danger": 0, "category": "运维",
     "method": "POST", "path": "/tools/query_cmdb_topology",
     "params_schema": [
         {"name": "app", "type": "string", "required": False, "desc": "应用名"},
     ]},
    {"id": "query_change_record", "name": "查询变更记录", "desc": "查询指定时间范围内服务相关变更工单", "icon": "📋", "tag": "只读查询", "danger": 0, "category": "运维",
     "method": "POST", "path": "/tools/query_change_record",
     "params_schema": [
         {"name": "service", "type": "string", "required": False, "desc": "服务名"},
         {"name": "hours", "type": "integer", "required": False, "desc": "回溯小时数"},
     ]},
    {"id": "query_alarm_info", "name": "查询历史告警", "desc": "按服务、时间范围检索告警事件列表及详情", "icon": "🚨", "tag": "只读查询", "danger": 0, "category": "运维",
     "method": "POST", "path": "/tools/query_alarm_info",
     "params_schema": [
         {"name": "service", "type": "string", "required": False, "desc": "服务名"},
     ]},
    {"id": "run_auto_job", "name": "执行自动化作业", "desc": "执行滚动重启、配置下发等变更操作", "icon": "⚠️", "tag": "高危写入", "danger": 1, "category": "运维",
     "method": "POST", "path": "/tools/run_auto_job",
     "params_schema": [
         {"name": "job_type", "type": "string", "required": False, "desc": "作业类型，restart/config"},
         {"name": "target", "type": "string", "required": False, "desc": "目标服务"},
     ]},
    {"id": "query_change_risk", "name": "变更风险预检查", "desc": "校验变更影响资产范围，评估风险等级", "icon": "⚙️", "tag": "只读查询", "danger": 0, "category": "运维",
     "method": "POST", "path": "/tools/query_change_risk",
     "params_schema": [
         {"name": "service", "type": "string", "required": False, "desc": "服务名"},
         {"name": "change", "type": "string", "required": False, "desc": "变更内容描述"},
     ]},
    {"id": "verify_service_status", "name": "变更后业务验证", "desc": "变更完成后校验服务健康状态", "icon": "✅", "tag": "只读查询", "danger": 0, "category": "运维",
     "method": "POST", "path": "/tools/verify_service_status",
     "params_schema": [
         {"name": "service", "type": "string", "required": False, "desc": "服务名"},
     ]},
    {"id": "search_slow_query", "name": "检索慢查询日志", "desc": "按数据库实例、时间范围检索慢查询SQL及执行时长", "icon": "🐢", "tag": "只读查询", "danger": 0, "category": "运维",
     "method": "POST", "path": "/tools/search_slow_query",
     "params_schema": [
         {"name": "instance", "type": "string", "required": False, "desc": "数据库实例"},
         {"name": "hours", "type": "integer", "required": False, "desc": "回溯小时数"},
     ]},
    {"id": "query_container_resource", "name": "查询容器资源画像", "desc": "采集K8s Pod的CPU/内存使用趋势与瓶颈", "icon": "📦", "tag": "只读查询", "danger": 0, "category": "运维",
     "method": "POST", "path": "/tools/query_container_resource",
     "params_schema": [
         {"name": "app", "type": "string", "required": False, "desc": "应用名"},
     ]},
    {"id": "scan_vulnerability", "name": "安全漏洞扫描", "desc": "对服务执行CVE漏洞扫描，输出风险等级", "icon": "🛡️", "tag": "只读查询", "danger": 0, "category": "运维",
     "method": "POST", "path": "/tools/scan_vulnerability",
     "params_schema": [
         {"name": "service", "type": "string", "required": False, "desc": "服务名"},
     ]},
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
]


MCP_SERVER_SEED = [
    # 本地 MCP Server：9010 MCP 工具网关（见 mcp_gateway.py），承载运维/经营/研发全部 26 个工具
    {
        "id": "mcp-gateway",
        "name": "NeuOps MCP 工具网关",
        "desc": "统一 MCP 工具网关（/tools 工具发现端点），承载运维/经营/研发全部 26 个工具",
        "base_url": "http://127.0.0.1:9010",
        "type": "gateway",
        "auth": "",
        "status": "online",
        "last_sync": "",
    },
]


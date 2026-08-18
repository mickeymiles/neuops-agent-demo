"""
Mock 数据文件 - MCP 工具网关的独立数据源
通过脚本更新此文件即可切换数据，无需改网关代码
所有数据与 9007 Demo 后端保持一致
"""
from datetime import datetime, timedelta


# ═══════════════════════════════════════════
# 业务指标 Mock
# ═══════════════════════════════════════════

MOCK_METRICS = {
    "order-service": {
        "qps": [120, 135, 158, 210, 287, 345, 312],
        "latency_p99": [45, 52, 68, 120, 245, 380, 420],
        "error_rate": [0.1, 0.2, 0.3, 0.8, 2.1, 3.5, 4.8],
        "cpu_usage": [35, 42, 55, 68, 78, 85, 92],
    },
    "payment-service": {
        "qps": [85, 92, 88, 95, 102, 98, 105],
        "latency_p99": [30, 35, 32, 38, 40, 36, 42],
        "error_rate": [0.05, 0.08, 0.06, 0.1, 0.09, 0.07, 0.11],
        "cpu_usage": [30, 33, 31, 36, 38, 35, 40],
    },
}

# ═══════════════════════════════════════════
# 服务日志 Mock
# ═══════════════════════════════════════════

MOCK_LOGS = [
    {"time": "2026-08-07 14:32:15", "level": "ERROR", "service": "order-service", "pod": "order-svc-pod-3",
     "message": "ConnectionTimeout: 连接数据库超时，host=db-master.neuops.internal:3306, timeout=5000ms"},
    {"time": "2026-08-07 14:32:18", "level": "ERROR", "service": "order-service", "pod": "order-svc-pod-3",
     "message": "SQLException: Too many connections, active=150, max=150"},
    {"time": "2026-08-07 14:32:22", "level": "ERROR", "service": "order-service", "pod": "order-svc-pod-1",
     "message": "CircuitBreaker: 熔断器打开，下游服务 payment-service 不可达"},
    {"time": "2026-08-07 14:32:25", "level": "WARN", "service": "order-service", "pod": "order-svc-pod-2",
     "message": "SlowQuery: SELECT * FROM orders WHERE status='PENDING' 耗时 8.2s"},
    {"time": "2026-08-07 14:33:01", "level": "ERROR", "service": "payment-service", "pod": "payment-svc-pod-2",
     "message": "ConnectionRefused: Redis 连接被拒绝 redis-cluster.neuops.internal:6379"},
    {"time": "2026-08-07 14:33:10", "level": "WARN", "service": "order-service", "pod": "order-svc-pod-1",
     "message": "RateLimiter: 限流触发，拒绝请求数=1,203/min"},
]

# ═══════════════════════════════════════════
# CMDB 资产拓扑 Mock
# ═══════════════════════════════════════════

MOCK_CMDB = {
    "order-service": {
        "app_id": "APP-ORDER-001", "name": "订单服务", "type": "微服务",
        "dependencies": ["payment-service", "user-service", "inventory-service"],
        "dependents": ["gateway-service", "web-portal"],
        "instances": 4, "version": "v3.2.1", "k8s_ns": "prod-order",
        "db": "MySQL 8.0 @ db-master.neuops.internal",
        "cache": "Redis Cluster @ redis-cluster.neuops.internal",
        "owner": "订单中心团队",
    },
    "payment-service": {
        "app_id": "APP-PAY-002", "name": "支付服务", "type": "微服务",
        "dependencies": ["bank-gateway", "user-service"],
        "dependents": ["order-service", "checkout-service"],
        "instances": 3, "version": "v2.8.0", "k8s_ns": "prod-payment",
        "db": "MySQL 8.0 @ db-payment.neuops.internal",
        "cache": "Redis Cluster @ redis-cluster.neuops.internal",
        "owner": "支付中心团队",
    },
}

# ═══════════════════════════════════════════
# 变更记录 Mock
# ═══════════════════════════════════════════

MOCK_CHANGES = [
    {"id": "CHG-20260807-001", "time": "2026-08-07 10:00", "type": "配置变更",
     "target": "db-master连接池", "detail": "max_connections 从 200 调整为 150",
     "operator": "张运维", "result": "成功"},
    {"id": "CHG-20260807-002", "time": "2026-08-07 08:30", "type": "版本发布",
     "target": "order-service v3.2.1", "detail": "灰度发布新版本，新增批量订单查询接口",
     "operator": "李开发", "result": "成功"},
    {"id": "CHG-20260806-003", "time": "2026-08-06 22:00", "type": "网络变更",
     "target": "prod-order 子网", "detail": "安全组规则更新，新增出站规则",
     "operator": "王网络", "result": "成功"},
    {"id": "CHG-20260806-004", "time": "2026-08-06 16:00", "type": "配置变更",
     "target": "Redis Cluster", "detail": "maxmemory 从 4GB 调整为 8GB",
     "operator": "张运维", "result": "成功"},
]

# ═══════════════════════════════════════════
# 告警信息 Mock
# ═══════════════════════════════════════════

MOCK_ALARMS = [
    {"id": "ALM-20260807-001", "time": "2026-08-07 14:33", "level": "P1-严重",
     "service": "order-service", "title": "订单服务响应延迟超过阈值",
     "detail": "P99延迟 420ms > 阈值 200ms，持续15分钟"},
    {"id": "ALM-20260807-002", "time": "2026-08-07 14:32", "level": "P2-警告",
     "service": "order-service", "title": "数据库连接池耗尽",
     "detail": "活跃连接数 150/150，新请求被拒绝"},
    {"id": "ALM-20260806-003", "time": "2026-08-06 23:15", "level": "P2-警告",
     "service": "payment-service", "title": "支付服务错误率上升",
     "detail": "错误率 5.2% > 阈值 1%，与Redis连接异常相关"},
]

# ═══════════════════════════════════════════
# 辅助函数 - 根据真实数据源动态生成时间戳
# ═══════════════════════════════════════════

def get_timestamps(count=7, interval_min=5):
    """生成最近 N 个时间点标签"""
    return [(datetime.now() - timedelta(minutes=interval_min * i)).strftime("%H:%M")
            for i in range(count, 0, -1)]


# ═══════════════════════════════════════════
# 项目管理域 Mock（两单一物/四算/工时/成本，全部只读研判）
# ═══════════════════════════════════════════

# 项目基础信息 + 里程碑 + 四算数据（单位：万元）
# 四算约束：概算 ≥ 预算 ≥ 核算 ≥ 决算；0 表示该阶段未发生
MOCK_PM_PROJECTS = [
    {"project_id": "P-2026-001", "name": "某银行一体化运维平台建设", "dept": "运维事业部",
     "manager": "赵经理", "status": "执行中", "start": "2026-03-01", "plan_end": "2026-09-30",
     "milestones": [
         {"name": "需求评审", "plan_date": "2026-03-15", "actual_date": "2026-03-14", "status": "done"},
         {"name": "架构设计", "plan_date": "2026-04-30", "actual_date": "2026-05-02", "status": "done"},
         {"name": "核心开发", "plan_date": "2026-07-31", "actual_date": "", "status": "running"},
         {"name": "UAT验收", "plan_date": "2026-08-31", "actual_date": "", "status": "overdue"},
         {"name": "上线结项", "plan_date": "2026-09-30", "actual_date": "", "status": "pending"},
     ],
     "four_calc": {"estimate": 520, "budget": 500, "accounting": 468, "final": 0},
     "members": [
         {"name": "张工", "role": "后端开发", "load_pct": 85},
         {"name": "李工", "role": "交付实施", "load_pct": 110},
         {"name": "王工", "role": "前端开发", "load_pct": 70},
     ]},
    {"project_id": "P-2026-002", "name": "某政务云监控体系建设项目", "dept": "政企事业部",
     "manager": "钱经理", "status": "执行中", "start": "2026-04-01", "plan_end": "2026-11-30",
     "milestones": [
         {"name": "需求评审", "plan_date": "2026-04-20", "actual_date": "2026-04-19", "status": "done"},
         {"name": "架构设计", "plan_date": "2026-05-31", "actual_date": "2026-06-05", "status": "done"},
         {"name": "核心开发", "plan_date": "2026-08-31", "actual_date": "", "status": "running"},
     ],
     "four_calc": {"estimate": 320, "budget": 300, "accounting": 315, "final": 0},
     "members": [
         {"name": "孙工", "role": "后端开发", "load_pct": 90},
         {"name": "周工", "role": "实施工程师", "load_pct": 95},
     ]},
    {"project_id": "P-2026-003", "name": "某制造企业IT运维外包项目", "dept": "运维事业部",
     "manager": "吴经理", "status": "已结项", "start": "2025-10-01", "plan_end": "2026-06-30",
     "milestones": [
         {"name": "需求评审", "plan_date": "2025-10-15", "actual_date": "2025-10-14", "status": "done"},
         {"name": "核心开发", "plan_date": "2026-02-28", "actual_date": "2026-02-26", "status": "done"},
         {"name": "UAT验收", "plan_date": "2026-04-30", "actual_date": "2026-05-02", "status": "done"},
         {"name": "上线结项", "plan_date": "2026-06-30", "actual_date": "2026-06-28", "status": "done"},
     ],
     "four_calc": {"estimate": 180, "budget": 175, "accounting": 160, "final": 152},
     "members": [
         {"name": "郑工", "role": "实施工程师", "load_pct": 0},
     ]},
    {"project_id": "P-2026-004", "name": "某医院智慧运维升级项目", "dept": "政企事业部",
     "manager": "冯经理", "status": "执行中", "start": "2026-05-01", "plan_end": "2026-12-31",
     "milestones": [
         {"name": "需求评审", "plan_date": "2026-05-20", "actual_date": "2026-05-21", "status": "done"},
         {"name": "架构设计", "plan_date": "2026-06-30", "actual_date": "", "status": "running"},
     ],
     "four_calc": {"estimate": 260, "budget": 280, "accounting": 0, "final": 0},
     "members": [
         {"name": "陈工", "role": "后端开发", "load_pct": 75},
         {"name": "褚工", "role": "实施工程师", "load_pct": 60},
     ]},
    {"project_id": "P-2026-005", "name": "某能源集团一体化运维项目", "dept": "运维事业部",
     "manager": "卫经理", "status": "已结项", "start": "2025-08-01", "plan_end": "2026-05-31",
     "milestones": [
         {"name": "上线结项", "plan_date": "2026-05-31", "actual_date": "2026-06-03", "status": "done"},
     ],
     "four_calc": {"estimate": 400, "budget": 390, "accounting": 370, "final": 378},
     "members": [
         {"name": "蒋工", "role": "实施工程师", "load_pct": 0},
     ]},
]

# 两单一物工单 / 任务明细（任务状态：pending/running/done/overdue）
MOCK_PM_TASKS = [
    {"task_id": "T-001-01", "project_id": "P-2026-001", "workorder": "WO-20260701",
     "title": "采集Agent部署", "assignee": "张工", "status": "done",
     "plan_date": "2026-07-05", "actual_date": "2026-07-06"},
    {"task_id": "T-001-02", "project_id": "P-2026-001", "workorder": "WO-20260701",
     "title": "告警降噪规则配置", "assignee": "李工", "status": "overdue",
     "plan_date": "2026-07-10", "actual_date": ""},
    {"task_id": "T-001-03", "project_id": "P-2026-001", "workorder": "WO-20260802",
     "title": "监控大盘搭建", "assignee": "张工", "status": "running",
     "plan_date": "2026-08-20", "actual_date": ""},
    {"task_id": "T-002-01", "project_id": "P-2026-002", "workorder": "WO-20260501",
     "title": "政务云纳管对接", "assignee": "孙工", "status": "running",
     "plan_date": "2026-08-25", "actual_date": ""},
    {"task_id": "T-002-02", "project_id": "P-2026-002", "workorder": "WO-20260501",
     "title": "网络设备探测", "assignee": "周工", "status": "pending",
     "plan_date": "2026-09-05", "actual_date": ""},
    {"task_id": "T-003-01", "project_id": "P-2026-003", "workorder": "WO-20251001",
     "title": "驻场运维服务", "assignee": "郑工", "status": "done",
     "plan_date": "2026-06-30", "actual_date": "2026-06-28"},
]

# 日报工时明细（status 标识合规质检结果：ok正常 / bad_fill敷衍 / empty空填 / overflow溢出 / missing少填 / wrong_bind错绑）
MOCK_PM_WORKHOURS = [
    {"date": "2026-08-14", "project_id": "P-2026-001", "employee": "张工", "hours": 8.0,
     "daily_content": "部署采集Agent至3台服务器，联调网络连通性，监控指标采集正常，无阻塞事项。",
     "task_ids": ["T-001-01"], "status": "ok"},
    {"date": "2026-08-14", "project_id": "P-2026-001", "employee": "李工", "hours": 8.0,
     "daily_content": "正常", "task_ids": [], "status": "bad_fill"},
    {"date": "2026-08-14", "project_id": "P-2026-001", "employee": "王工", "hours": 12.0,
     "daily_content": "完成监控大盘首页图表，联调接口，修复样式问题，补充数据刷新逻辑，测试通过。",
     "task_ids": ["T-001-03"], "status": "overflow"},
    {"date": "2026-08-13", "project_id": "P-2026-001", "employee": "赵工", "hours": 0.0,
     "daily_content": "", "task_ids": [], "status": "missing"},
    {"date": "2026-08-14", "project_id": "P-2026-002", "employee": "孙工", "hours": 8.0,
     "daily_content": "完成政务云API对接联调，处理鉴权问题，进度正常。",
     "task_ids": ["T-002-01"], "status": "ok"},
    {"date": "2026-08-14", "project_id": "P-2026-002", "employee": "周工", "hours": 8.0,
     "daily_content": "整理网络拓扑资料", "task_ids": ["T-002-02"], "status": "bad_fill"},
]

# 项目人力成本折算（单位：万元；cost_rate=人日单价万元）
MOCK_PM_COSTS = [
    {"project_id": "P-2026-001", "period": "2026-08", "total_man_days": 520, "cost_rate": 0.15,
     "human_cost": 78.0, "cum_human_cost": 468.0, "budget": 500.0, "budget_left": 32.0,
     "contract_amount": 560.0, "target_profit_rate": 0.12, "real_profit_rate": 0.118},
    {"project_id": "P-2026-002", "period": "2026-08", "total_man_days": 350, "cost_rate": 0.15,
     "human_cost": 52.5, "cum_human_cost": 315.0, "budget": 300.0, "budget_left": -15.0,
     "contract_amount": 330.0, "target_profit_rate": 0.10, "real_profit_rate": 0.045},
    {"project_id": "P-2026-003", "period": "2026-06", "total_man_days": 120, "cost_rate": 0.14,
     "human_cost": 16.8, "cum_human_cost": 160.0, "budget": 175.0, "budget_left": 15.0,
     "contract_amount": 195.0, "target_profit_rate": 0.15, "real_profit_rate": 0.179},
]

# 集团考核预计算指标（人均效/元效/双按完成率/四算偏差）
MOCK_BIZ_METRICS = {
    "人均效": {"period": "2026-07", "value": 12.6, "target": 12.0, "unit": "万元/人/月", "trend": "up",
              "note": "人均创效高于目标，达标"},
    "元效": {"period": "2026-07", "value": 1.8, "target": 2.0, "unit": "元收益/元投入", "trend": "down",
             "note": "低于目标值，需关注成本投入产出"},
    "双按完成率": {"period": "2026-07", "value": {"按期完成率": 0.86, "按预算完成率": 0.92},
                "target": {"按期完成率": 0.90, "按预算完成率": 0.90}, "unit": "%", "trend": "mixed",
                "note": "按预算完成率达标，按期完成率略低于目标"},
    "按期完成率": {"period": "2026-07", "value": 0.86, "target": 0.90, "unit": "%", "trend": "down",
                "note": "低于目标，存在逾期交付项目"},
    "按预算完成率": {"period": "2026-07", "value": 0.92, "target": 0.90, "unit": "%", "trend": "up",
                  "note": "达标"},
    "四算偏差": {"period": "2026-07", "value": {"越界项目数": 3, "超预算项目": ["P-2026-002"], "超概算项目": ["P-2026-004"], "决算超核算项目": ["P-2026-005"]},
               "note": "本月识别3个集团风险项目，详见四算对比台账"},
}


# ═══════════════════════════════════════════
# 售前投标域 Mock（知识库/历史方案/模板，只生成不执行）
# ═══════════════════════════════════════════

# 内部知识库 / 历史方案 / 中标库
MOCK_BID_KB = [
    {"id": "KB-001", "industry": "金融/银行", "scenario": "一体化运维平台建设", "title": "某银行一体化运维平台技术方案",
     "summary": "全栈监控+告警降噪+自动化运维一体化方案，中标金额680万",
     "amount": 680, "win": True, "keywords": ["银行", "监控", "运维平台", "告警", "自动化"],
     "content": "方案围绕银行核心系统统一监控（服务器/数据库/中间件/网络）、智能告警降噪、自动化巡检与自愈展开，"
                "含4层可观测体系与7大数字员工建设路径，满足金融行业合规要求。"},
    {"id": "KB-002", "industry": "政务", "scenario": "云监控体系建设", "title": "某政务云监控体系建设方案",
     "summary": "政务云资源纳管+网络探测+合规审计方案，中标金额420万",
     "amount": 420, "win": True, "keywords": ["政务云", "纳管", "网络探测", "合规"],
     "content": "方案聚焦政务云资源统一纳管、网络设备探测、安全合规审计与属地化交付。"},
    {"id": "KB-003", "industry": "制造", "scenario": "IT运维外包", "title": "某制造企业IT运维外包方案",
     "summary": "驻场运维+SLA分级响应+季度巡检报告体系，中标金额195万",
     "amount": 195, "win": True, "keywords": ["外包", "驻场", "SLA", "巡检"],
     "content": "方案包含驻场服务团队、SLA分级响应、季度巡检与考核指标看板。"},
    {"id": "KB-004", "industry": "能源", "scenario": "一体化运维项目", "title": "某能源集团一体化运维方案（未中标）",
     "summary": "因报价过高未中标，技术部分获评优秀",
     "amount": 0, "win": False, "keywords": ["能源", "运维", "集团"],
     "content": "方案技术部分获评优秀，商务报价高于竞争对手12%，复盘结论：控制集成类成本报价。"},
    {"id": "KB-005", "industry": "医疗", "scenario": "智慧运维升级", "title": "某医院智慧运维升级方案（编写中）",
     "summary": "基于统一监控平台叠加AI运维能力，含等保合规改造",
     "amount": 0, "win": False, "keywords": ["医院", "智慧运维", "等保", "AI"],
     "content": "方案含等保合规改造、智慧运维能力升级与医疗核心系统专项保障。"},
]

# 投标标准模板库 / 技术规范模板
MOCK_BID_TEMPLATES = {
    "tech_proposal": {"name": "技术方案建议书模板", "version": "v2.3",
                      "sections": ["项目背景与需求理解", "总体架构设计", "功能方案说明", "技术指标响应", "实施与服务保障", "项目团队与资质"]},
    "response": {"name": "招标点对点应答模板", "version": "v1.8",
                 "sections": ["商务应答", "技术应答", "偏离表", "证明材料索引"]},
    "ppt_outline": {"name": "售前汇报PPT大纲模板", "version": "v2.0",
                    "sections": ["封面与公司简介", "客户痛点与需求理解", "方案总体架构", "核心亮点", "实施路径", "成功案例", "Q&A"]},
    "impl_plan": {"name": "实施方案模板", "version": "v1.5",
                  "sections": ["项目范围与目标", "实施组织与计划", "详细实施步骤", "风险管理", "验收标准与交付物"]},
}

# ────────────────────────────────────────────
# Mock 数据
# ────────────────────────────────────────────

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

MOCK_LOGS = [
    {"time": "2026-08-07 14:32:15", "level": "ERROR", "service": "order-service", "pod": "order-svc-pod-3", "message": "ConnectionTimeout: 连接数据库超时，host=db-master.neuops.internal:3306, timeout=5000ms"},
    {"time": "2026-08-07 14:32:18", "level": "ERROR", "service": "order-service", "pod": "order-svc-pod-3", "message": "SQLException: Too many connections, active=150, max=150"},
    {"time": "2026-08-07 14:32:22", "level": "ERROR", "service": "order-service", "pod": "order-svc-pod-1", "message": "CircuitBreaker: 熔断器打开，下游服务 payment-service 不可达"},
    {"time": "2026-08-07 14:32:25", "level": "WARN", "service": "order-service", "pod": "order-svc-pod-2", "message": "SlowQuery: SELECT * FROM orders WHERE status='PENDING' 耗时 8.2s"},
    {"time": "2026-08-07 14:33:01", "level": "ERROR", "service": "payment-service", "pod": "payment-svc-pod-2", "message": "ConnectionRefused: Redis 连接被拒绝 redis-cluster.neuops.internal:6379"},
    {"time": "2026-08-07 14:33:10", "level": "WARN", "service": "order-service", "pod": "order-svc-pod-1", "message": "RateLimiter: 限流触发，拒绝请求数=1,203/min"},
]

MOCK_CMDB = {
    "order-service": {
        "app_id": "APP-ORDER-001",
        "name": "订单服务",
        "type": "微服务",
        "dependencies": ["payment-service", "user-service", "inventory-service"],
        "dependents": ["gateway-service", "web-portal"],
        "instances": 4,
        "version": "v3.2.1",
        "k8s_ns": "prod-order",
        "db": "MySQL 8.0 @ db-master.neuops.internal",
        "cache": "Redis Cluster @ redis-cluster.neuops.internal",
        "owner": "订单中心团队",
    },
    "payment-service": {
        "app_id": "APP-PAY-002",
        "name": "支付服务",
        "type": "微服务",
        "dependencies": ["bank-gateway", "user-service"],
        "dependents": ["order-service", "checkout-service"],
        "instances": 3,
        "version": "v2.8.0",
        "k8s_ns": "prod-payment",
        "db": "MySQL 8.0 @ db-payment.neuops.internal",
        "cache": "Redis Cluster @ redis-cluster.neuops.internal",
        "owner": "支付中心团队",
    },
}

MOCK_CHANGES = [
    {"id": "CHG-20260807-001", "time": "2026-08-07 10:00", "type": "配置变更", "target": "db-master连接池", "detail": "max_connections 从 200 调整为 150", "operator": "张运维", "result": "成功"},
    {"id": "CHG-20260807-002", "time": "2026-08-07 08:30", "type": "版本发布", "target": "order-service v3.2.1", "detail": "灰度发布新版本，新增批量订单查询接口", "operator": "李开发", "result": "成功"},
    {"id": "CHG-20260806-003", "time": "2026-08-06 22:00", "type": "网络变更", "target": "prod-order 子网", "detail": "安全组规则更新，新增出站规则", "operator": "王网络", "result": "成功"},
    {"id": "CHG-20260806-004", "time": "2026-08-06 16:00", "type": "配置变更", "target": "Redis Cluster", "detail": "maxmemory 从 4GB 调整为 8GB", "operator": "张运维", "result": "成功"},
]

MOCK_ALARMS = [
    {"id": "ALM-20260807-001", "time": "2026-08-07 14:33", "level": "P1-严重", "service": "order-service", "title": "订单服务响应延迟超过阈值", "detail": "P99延迟 420ms > 阈值 200ms，持续15分钟"},
    {"id": "ALM-20260807-002", "time": "2026-08-07 14:32", "level": "P2-警告", "service": "order-service", "title": "数据库连接池耗尽", "detail": "活跃连接数 150/150，新请求被拒绝"},
    {"id": "ALM-20260806-003", "time": "2026-08-06 23:15", "level": "P2-警告", "service": "payment-service", "title": "支付服务错误率上升", "detail": "错误率 5.2% > 阈值 1%，与Redis连接异常相关"},
]

MOCK_KNOWLEDGE = [
    {"title": "订单服务故障处理手册 v3.2", "summary": "涵盖订单服务常见故障场景：数据库连接超时、熔断器触发、消息队列积压等应急处理流程。", "score": 0.92},
    {"title": "数据库连接池配置最佳实践", "summary": "介绍MySQL连接池参数调优方法，包括max_connections、wait_timeout等关键参数设置建议。", "score": 0.87},
    {"title": "微服务熔断降级策略指南", "summary": "Sentinel/Hystrix熔断策略配置规范，含半开状态恢复机制说明和监控告警阈值建议。", "score": 0.83},
    {"title": "Redis集群故障排查手册", "summary": "Redis Cluster常见问题：节点失联、数据倾斜、内存淘汰、慢查询等问题的定位和恢复方法。", "score": 0.78},
    {"title": "变更管理规范与回滚流程", "summary": "线上变更审批流程、灰度发布策略、回滚操作手册及变更窗口规定。", "score": 0.75},
]

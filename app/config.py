# -*- coding: utf-8 -*-
"""NeuOps Agent Demo 全局配置：路径 / 端口 / 常量

拆分自原 main.py 的模块级常量，保持行为 100% 兼容。
"""
import os

# 项目根目录（neuops-agent-demo/）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# SQLite 数据库文件（保持在项目根目录，与原 main.py 行为一致）
DB_PATH = os.path.join(BASE_DIR, "neuops_sessions.db")

# 静态资源目录（主界面 index.html / monitor.html）
STATIC_DIR = os.path.join(BASE_DIR, "static")

# 服务端口
PORT = 9007

# 研发专家 emp-005 的文件工具：9006 系统代码根目录
DEV_9006_ROOT = "/home/ubuntu/contract-compare"
DEV_ALLOWED_SUBDIRS = ("backend", "frontend", "docs")

# 9006 系统（业务系统 / ETL 任务）地址
ETL_9006_BASE = "http://127.0.0.1:9006"
BIZ_9006_BASE = "http://127.0.0.1:9006"

# DeepSeek 真实 LLM 调用层
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = "deepseek-v4-pro"

# DeepSeek 成本估算单价（元 / 百万 tokens）
COST_INPUT_PER_M = 2.0
COST_OUTPUT_PER_M = 3.0

# ═══════════════════════════════════════════
# 统一监控探针（app/probe）配置
# ═══════════════════════════════════════════

# 探针采集周期（秒）：服务器/容器/数据库/中间件/应用/网络 六类统一调度
OPS_PROBE_INTERVAL = 30
# 时序指标保留天数（默认 1 天，按天自动清理）
OPS_RETENTION_DAYS = 1

# 统一日志采集（log_collector）
# 应用日志文件路径默认值；实际路径可通过 /ops 配置中心覆盖（settings 表 app_9006_log / app_9007_log）
LOG_DEFAULT_9006 = ""
LOG_DEFAULT_9007 = ""
# 每轮每个日志源最多读取行数（增量 tail）
LOG_MAX_LINES_PER_RUN = 300
# 日志告警：最近窗口内 error 级别条数阈值
LOG_ERROR_WINDOW_MIN = 5
LOG_ERROR_THRESHOLD = 10

# 代码级自愈（ops_code_heal）
CODE_HEAL_ENABLED = True
# 代码仓库路径（默认当前项目根目录；可通过 settings 页面配置 app_code_repo）
CODE_REPO_DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
# 代码自愈操作步骤超时（秒）
CODE_HEAL_STEP_TIMEOUT = 120
# 修复后健康验证的超时与重试
CODE_HEAL_VERIFY_TIMEOUT = 60
# LLM 修复引擎预留（配置 code_heal_llm_url / code_heal_llm_key 后自动启用，否则使用规则修复器）
CODE_HEAL_LLM_URL = ""
CODE_HEAL_LLM_KEY = ""
# 补丁白名单：仅允许修改仓库内这些前缀路径（安全护栏）
CODE_HEAL_ALLOW_PREFIXES = ("app/", "static/", "tests/", "requirements.txt",
                            "scripts/", "run.sh")

# 9006 业务系统（contract-compare）健康检查
APP_9006_NAME = "contract-compare"
APP_9006_BASE = "http://127.0.0.1:9006"
APP_9006_HEALTH_PATH = "/"

# neuops 自身（监控平台）健康检查
APP_NEUOPS_NAME = "neuops-agent"
APP_NEUOPS_BASE = f"http://127.0.0.1:{PORT}"
APP_NEUOPS_HEALTH_PATH = "/"

# 9006 系统数据库候选检测路径（服务器实证后按需调整）
DB_9006_SQLITE_CANDIDATES = (
    "/home/ubuntu/contract-compare/backend/contract.db",
    "/home/ubuntu/contract-compare/contract.db",
    "/home/ubuntu/contract-compare/backend/data/contract.db",
    "/home/ubuntu/contract-compare/data/contract.db",
    "/home/ubuntu/contract-compare/backend/app.db",
)
DB_9006_MYSQL_PORT = 3306
DB_9006_PG_PORT = 5432

# 探针采集的中间件候选（端口探测 + 进程识别，命中才登记为实体）
MIDDLEWARE_PROBES = (
    {"name": "redis", "label": "Redis", "ports": (6379,)},
    {"name": "mysql", "label": "MySQL", "ports": (3306,)},
    {"name": "postgresql", "label": "PostgreSQL", "ports": (5432,)},
    {"name": "nginx", "label": "Nginx", "ports": (80, 443)},
    {"name": "rabbitmq", "label": "RabbitMQ", "ports": (5672, 15672)},
    {"name": "kafka", "label": "Kafka", "ports": (9092,)},
    {"name": "elasticsearch", "label": "Elasticsearch", "ports": (9200,)},
    {"name": "mongodb", "label": "MongoDB", "ports": (27017,)},
)

# 探针独立 CLI 上报地址（预留：远程探针部署到目标机后，通过 HTTP 上报给监控中心）
PROBE_REPORT_URL = ""

# 飞书告警（预留：webhook 从 settings 表读取，页面可配置）
FEISHU_WEBHOOK_DEFAULT = ""

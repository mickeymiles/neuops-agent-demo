# -*- coding: utf-8 -*-
"""NeuOps Agent Demo 全局配置：路径 / 端口 / 常量

拆分自原 main.py 的模块级常量，保持行为 100% 兼容。
"""
import os

# ── .env 自动加载（无需 python-dotenv 依赖）────────────────────────
def _load_env_file():
    """从项目根目录 .env 文件加载环境变量（已 gitignore，不推 GitHub）"""
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, val = line.partition("=")
                key, val = key.strip(), val.strip()
                if key and key not in os.environ:
                    os.environ[key] = val

_load_env_file()

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
# 后端内部调用地址（默认同机 127.0.0.1，部署时可用环境变量覆盖）
ETL_9006_BASE = os.getenv("ETL_9006_BASE", "http://127.0.0.1:9006")
BIZ_9006_BASE = os.getenv("BIZ_9006_BASE", "http://127.0.0.1:9006")
# 前端外链公开地址（后台管理页面注入用）：
# 默认指向生产服务器 122.51.98.98 的 9006 业务平台；
# 本地开发可设 BIZ_9006_PUBLIC_BASE=http://127.0.0.1:9006 覆盖；
# 置空则后端按浏览器访问主机自动推导（见 routes_manage.py）
BIZ_9006_PUBLIC_BASE = os.getenv("BIZ_9006_PUBLIC_BASE", "http://122.51.98.98:9006")

# DeepSeek 真实 LLM 调用层
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = "deepseek-v4-flash"

# ═══════════════════════════════════════════
# DSH 内核引擎（DeepSeek Harness）配置
# ═══════════════════════════════════════════
# 聊天引擎分发：legacy（默认，现有手写 Agent 循环）| dsh（DeepSeek Harness 内核）
AGENT_ENGINE = os.getenv("AGENT_ENGINE", "legacy")
# dsh CLI 路径：留空则依次尝试 PATH 中的 dsh / ~/.npm/_npx/*/node_modules/.bin/dsh
DSH_BIN = os.getenv("DSH_BIN", "")
# dsh profile（headless = 一次性任务执行，不监听端口）
DSH_PROFILE = os.getenv("DSH_PROFILE", "headless")
# 单任务执行超时（秒）
DSH_TIMEOUT = float(os.getenv("DSH_TIMEOUT", "300"))
# 拼进任务的最近历史条数（每轮 = 1 user + 1 assistant，共 2 条）
DSH_MAX_HISTORY = int(os.getenv("DSH_MAX_HISTORY", "6"))
# DSH 数据目录（含 profiles / .credentials.yaml）
DSH_HOME = os.getenv("DSH_HOME", os.path.expanduser("~/.dsh"))

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

# 9006 业务系统（contract-compare）健康检查
APP_9006_NAME = "contract-compare"
APP_9006_BASE = "http://127.0.0.1:9006"
APP_9006_HEALTH_PATH = "/"

# neuops 自身（监控平台）健康检查
APP_NEUOPS_NAME = "neuops-agent"
APP_NEUOPS_BASE = f"http://127.0.0.1:{PORT}"
APP_NEUOPS_HEALTH_PATH = "/"

# 探针应用发现：端口 → 应用名提示
# 通用探测原则：探针动态发现本机监听端口并做 HTTP 探测，"有什么就监视什么"，
# 仅在对应端口被监听时用此映射识别应用名（本机不存在则不登记，不产生误报）。
APP_PORT_HINTS = {
    9006: "contract-compare",
    9007: "neuops-agent",
}

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

# ═══════════════════════════════════════════
# 备品备件采购询比价智能体（emp-008）配置
# ═══════════════════════════════════════════
# 邮件账号（IMAP 收件 + SMTP 发件），163 邮箱
PROC_MAIL_USERNAME = os.getenv("PROC_MAIL_USERNAME", "")
PROC_MAIL_PASSWORD = os.getenv("PROC_MAIL_PASSWORD", "")  # 163 邮箱授权码
PROC_MAIL_IMAP_HOST = "imap.163.com"
PROC_MAIL_IMAP_PORT = 993
PROC_MAIL_SMTP_HOST = "smtp.163.com"
PROC_MAIL_SMTP_PORT = 465

# ── 本体轨（ont-emp009）独立邮箱 ────────────────────────────────
# 双轨并行：现轨 emp-008 走 PROC_MAIL_*，本体轨走 ONT_MAIL_*，两套收发互不干扰。
# 未显式配置时回退到现轨账号（保持单轨行为不变）；
# 但双轨并行必须显式配置 ONT_MAIL_USERNAME/PASSWORD，否则两套会抢同一个收件箱
# （现轨用 UNSEEN 增量扫描，本体轨会 mark_seen 认领，共用邮箱必然互相漏单）。
ONT_MAIL_USERNAME = os.getenv("ONT_MAIL_USERNAME", "") or PROC_MAIL_USERNAME
ONT_MAIL_PASSWORD = os.getenv("ONT_MAIL_PASSWORD", "") or PROC_MAIL_PASSWORD
ONT_MAIL_IMAP_HOST = os.getenv("ONT_MAIL_IMAP_HOST", PROC_MAIL_IMAP_HOST)
ONT_MAIL_IMAP_PORT = int(os.getenv("ONT_MAIL_IMAP_PORT", str(PROC_MAIL_IMAP_PORT)))
ONT_MAIL_SMTP_HOST = os.getenv("ONT_MAIL_SMTP_HOST", PROC_MAIL_SMTP_HOST)
ONT_MAIL_SMTP_PORT = int(os.getenv("ONT_MAIL_SMTP_PORT", str(PROC_MAIL_SMTP_PORT)))
# 本体轨发件显示名（智能体本体身份，b4）。与现轨区分，便于在供应商/审批人邮箱里一眼分辨来源
ONT_MAIL_DISPLAY_NAME = os.getenv("ONT_MAIL_DISPLAY_NAME", "采购智能体")
# 本体轨专用参与者：供应商（逗号分隔 姓名:邮箱，如 "华为:b2@163.com,XX:b6@163.com"）
# 与审批人（逗号分隔邮箱）。留空则回退现轨 proc_participants。
ONT_SUPPLIERS = os.getenv("ONT_SUPPLIERS", "")
ONT_APPROVERS = os.getenv("ONT_APPROVERS", "")
# 询价发起人白名单（逗号分隔邮箱或 @域名）。留空 = 不限制（向后兼容）。
# 不限制时，任何含「询价/采购/备件/购买」且非回复的邮件都会被认领建任务——
# 「采购」是极常见词，广告/垃圾邮件极易误触发，生产环境务必配置。
ONT_REQUESTERS = os.getenv("ONT_REQUESTERS", "")
# 认领扫描窗口下界（小时）。实际下界 = min(now-该值, 水位-缓冲)，水位用于停机后补扫防漏。
ONT_SCAN_HOURS = int(os.getenv("ONT_SCAN_HOURS", "48"))

# 飞书应用凭据（emp-008 发送飞书通知）
PROC_FEISHU_APP_ID = os.getenv("PROC_FEISHU_APP_ID", "")
PROC_FEISHU_APP_SECRET = os.getenv("PROC_FEISHU_APP_SECRET", "")
# 项目经理飞书 open_id（接收消息的人，待用户提供）
PROC_FEISHU_PM_OPEN_ID = os.getenv("PROC_FEISHU_PM_OPEN_ID", "")
# 飞书多维表格 app_token（待用户提供；3 张表的 table_id 见下）
PROC_FEISHU_BITABLE_APP_TOKEN = os.getenv("PROC_FEISHU_BITABLE_APP_TOKEN", "")
PROC_FEISHU_BITABLE_TASK_TABLE_ID = os.getenv("PROC_FEISHU_BITABLE_TASK_TABLE_ID", "")
PROC_FEISHU_BITABLE_LEDGER_TABLE_ID = os.getenv("PROC_FEISHU_BITABLE_LEDGER_TABLE_ID", "")

# 9006 工程数据库（contract-compare-9006 SQLite，emp-008 直读采购任务/台账/主数据）
# 注意：procurement_models.py 的 DB_PATH = contract-compare-9006/contract_compare.db（工程根目录，非 backend/）
PROC_9006_DB_PATH = os.getenv(
    "PROC_9006_DB_PATH",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                 "contract-compare", "contract_compare.db"),
)
# 9006 后端 API（contract-compare-9006）
PROC_9006_BASE = os.getenv("PROC_9006_BASE", "http://127.0.0.1:9006")


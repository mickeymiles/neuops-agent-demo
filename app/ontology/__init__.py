# -*- coding: utf-8 -*-
"""本体轨（NO-012 emp-009）：基于实体的 LLM 自主决策轨道（独立于现轨）。

落库后端由 `ONT_STORE_BACKEND` 决定（在 `from . import store` 之前完成绑定，
这样各子模块里的 `from . import store` 会直接拿到这里选定的后端）：

  biz（默认）  → store_biz：写 9006 业务主表 procurement_task
                 备件采购已剥离本体，按普通业务逻辑流转
  ontology     → store：写本体 ABox（contract_ontology.db 的 o_task）
"""
import os

from . import schema

# 业务化链路不再依赖本体 ABox 的表结构，建表失败不应阻断启动
try:
    schema.ensure_core_tables()
except Exception:
    pass

_STORE_BACKEND = (os.getenv("ONT_STORE_BACKEND", "biz") or "biz").strip().lower()
if _STORE_BACKEND == "ontology":
    from . import store  # noqa: F401  本体 ABox 落库
else:
    from . import store_biz as store  # noqa: F401  9006 业务主表落库


def init():
    try:
        schema.ensure_core_tables()
    except Exception:
        pass
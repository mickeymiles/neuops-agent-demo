# -*- coding: utf-8 -*-
"""测试环境隔离。

单元测试用合成邮箱地址（eng@x.com / s1@x.com …），不应受 `.env` 里生产配置影响。
尤其 ONT_REQUESTERS（询价发起人白名单）一旦在 .env 配了真实地址，
所有用合成地址的用例都会被白名单挡住——那是环境串味，不是代码缺陷。
这里统一把白名单置空，需要验证白名单本身的用例请显式传 allow_senders 参数
（见 tests/test_ont_claim.py）。

另外：落库后端默认走 9006 业务主表（ONT_STORE_BACKEND=biz）。若不隔离，
用例会把测试数据写进开发机的真实 9006 库，且邮件 message_id 一旦落库
后续轮次会被去重跳过（表现为「第一次跑绿、第二次全红」）。
故这里把 PROC_9006_DB_PATH 指向会话级临时库，由 store_biz 自动建表。
"""
import os
import pytest
import tempfile


@pytest.fixture(autouse=True, scope="session")
def _isolate_env_from_dotenv():
    import app.config as cfg
    saved = getattr(cfg, "ONT_REQUESTERS", "")
    cfg.ONT_REQUESTERS = ""
    yield
    cfg.ONT_REQUESTERS = saved


@pytest.fixture(autouse=True)
def _isolate_biz_db(tmp_path, monkeypatch):
    """业务落库指向**每个用例**独立的临时库。

    必须与各测试文件里本体库的 `_fresh` fixture 保持同级别隔离：
    若业务库跨用例共享，前一个用例写入的 task / 邮件 message_id 会残留，
    后续用例被去重跳过（表现为「单独跑绿、整轮跑红」）。
    """
    from app.ontology import store_biz
    path = str(tmp_path / "biz.db")
    # 先建空文件：store_biz 连接前会校验 exists（避免误建垃圾库）
    with open(path, "wb"):
        pass
    monkeypatch.setenv("PROC_9006_DB_PATH", path)
    store_biz._schema_ready = False
    yield
    store_biz._schema_ready = False

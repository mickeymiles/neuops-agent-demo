# -*- coding: utf-8 -*-
"""测试环境隔离。

单元测试用合成邮箱地址（eng@x.com / s1@x.com …），不应受 `.env` 里生产配置影响。
尤其 ONT_REQUESTERS（询价发起人白名单）一旦在 .env 配了真实地址，
所有用合成地址的用例都会被白名单挡住——那是环境串味，不是代码缺陷。
这里统一把白名单置空，需要验证白名单本身的用例请显式传 allow_senders 参数
（见 tests/test_ont_claim.py）。
"""
import pytest


@pytest.fixture(autouse=True, scope="session")
def _isolate_env_from_dotenv():
    import app.config as cfg
    saved = getattr(cfg, "ONT_REQUESTERS", "")
    cfg.ONT_REQUESTERS = ""
    yield
    cfg.ONT_REQUESTERS = saved

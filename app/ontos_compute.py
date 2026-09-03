# -*- coding: utf-8 -*-
"""本体计算（demo 直调共享 ontos 子模块，无 9006 依赖）。

智能体平台（探索 / 溯源 / 模拟 / 预测等临时口径分析）直接 import 同一份 ontos TBox
纯函数，与 9006 固化显示调用同一算法，杜绝口径漂移。

用法：
    from app.ontos_compute import compute, list_functions
    compute('payment_cycle', {'sign_date': '2024-01-01',
                             'receipts': [{'received_date': '2024-05-01'}]})
"""
import os
import sys

# 共享 ontos 子模块位于 <repo>/ontos（内含 ontos/ 包）
_ONTOS_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "ontos"))


def _ensure_ontos_importable():
    if _ONTOS_ROOT not in sys.path:
        sys.path.insert(0, _ONTOS_ROOT)


def compute(function: str, params: dict = None) -> dict:
    """直接计算本体 F-* 纯函数，返回 ontos.dispatch 的结构化结果。

    function: 函数名 或 F-xxx（'payment_cycle' / 'F-payment-cycle' 等价）
    params  : 参数字典（如 {'sign_date':'2024-01-01','receipts':[{'received_date':'2024-05-01'}]}）
    返回    : {'success': bool, 'function': str, 'result': <原函数返回值>}
    """
    _ensure_ontos_importable()
    from ontos import domain_business as biz
    return biz.dispatch(function, params or {})


def list_functions() -> list:
    """列出可计算函数（含参数签名），供 agent 发现。"""
    _ensure_ontos_importable()
    from ontos import domain_business as biz
    return biz.list_compute_functions()

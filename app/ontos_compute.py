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

    ★ABox 场景函数（2026-09-05 用户拍板：同源）：cost_warning_portfolio 等
    由 ontos.abox_cost（共享 ABox 适配层）直读业务库 SQLite 计算——
    **不经 9006 的 HTTP API**，与 9006 固化页面同一份实现，杜绝口径漂移。
    数据库路径解析优先级：params.db_path > 环境变量 ONTOS_DB_PATH > 同仓默认路径
    （服务器上 9006 与本服务同机，直读同一份 contract_compare.db，只读）。
    """
    fn = (function or '').strip()
    if fn in ABOX_SCENARIO_FUNCTIONS:
        return _compute_abox(fn, params or {})
    _ensure_ontos_importable()
    from ontos import domain_business as biz
    return biz.dispatch(function, params or {})


# ── ABox 场景函数注册（读真实业务数据，非纯函数）─────────────────
# 智能体经 ontology_compute 工具调用；数据/判定均出自共享 ontos 仓的 abox_cost 模块。
ABOX_SCENARIO_FUNCTIONS = {
    'cost_warning_portfolio': '全量成本预警（读 md_contract，返回 summary+rows，'
                              '支持 contract_no 参数查单项目）',
    'cost_warning_all': 'cost_warning_portfolio 别名（9006 同名入口）',
}

# 默认业务库路径：服务器上 9006 部署于本仓库同级 ../contract-compare/
_DEFAULT_DB = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', 'contract-compare', 'contract_compare.db'))


def _abox_db_path(params: dict) -> str:
    """ABox 数据库路径解析：params.db_path > 环境变量 ONTOS_DB_PATH > 同仓默认路径。"""
    p = (params or {}).get('db_path') or os.getenv('ONTOS_DB_PATH') or _DEFAULT_DB
    return str(p)


def _compute_abox(fn: str, params: dict) -> dict:
    """ABox 场景计算：调共享 ontos.abox_cost（读 SQLite 业务库 → F-* 判定）。"""
    db_path = _abox_db_path(params)
    params = {k: v for k, v in (params or {}).items() if k != 'db_path'}
    if not os.path.exists(db_path):
        return {'success': False, 'function': fn,
                'error': 'abox_db_not_found',
                'message': f'业务库不存在：{db_path}（请设置环境变量 ONTOS_DB_PATH '
                           f'指向 contract-compare 的 contract_compare.db）'}
    _ensure_ontos_importable()
    from ontos import abox_cost
    try:
        if fn == 'cost_warning_portfolio' or fn == 'cost_warning_all':
            result = abox_cost.cost_warning_portfolio(
                db_path, contract_no=params.get('contract_no') or None)
            return {'success': True, 'function': 'cost_warning_portfolio', 'result': result}
        return {'success': False, 'function': fn, 'error': 'unknown_abox_function'}
    except Exception as e:
        return {'success': False, 'function': fn, 'error': type(e).__name__,
                'message': str(e)}


def list_functions() -> list:
    """列出可计算函数（含参数签名），供 agent 发现。

    含 ABox 场景函数（kind='abox'，读真实业务数据；纯函数 kind='function'）。
    """
    _ensure_ontos_importable()
    from ontos import domain_business as biz
    out = list(biz.list_compute_functions())
    out.extend([
        {'id': fid, 'kind': 'abox', 'name': fid, 'description': desc,
         'params': {'contract_no': '可选，指定合同编号则只算该项目'},
         'note': '读业务库 md_contract（共享 ontos.abox_cost，与 9006 同源）'}
        for fid, desc in ABOX_SCENARIO_FUNCTIONS.items()
    ])
    return out

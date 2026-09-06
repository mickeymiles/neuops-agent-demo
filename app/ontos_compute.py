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
                              '支持 contract_no 参数查单项目；已含预估口径：有效成本=当前成本+预估成本)',
    'cost_warning_all': 'cost_warning_portfolio 别名（9006 同名入口）',
    'project_facts': '项目档案（读 md_contract）：档案列 + 预算/成本 + 本体预警判定，'
                     '每条含 est_cost(预估成本)/wo_est_cost；支持 contract_no 查单项目',
    'project_portfolio': '项目组合查询（条目 + 全库总数/截断标记/全量预警分布）；'
                         '支持 contract_no/status 过滤，防把样本当全集',
    'cost_detail': '成本明细：预算三分量 / 成本六分量 + 本体预警；支持 contract_no',
}

# 默认业务库路径：服务器上 9006 部署于本仓库同级 ../contract-compare/
_DEFAULT_DB = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', 'contract-compare', 'contract_compare.db'))


def _abox_db_path(params: dict = None) -> str:
    """ABox 数据库路径解析：params.db_path > 环境变量 ONTOS_DB_PATH > 同仓默认路径。"""
    p = (params or {}).get('db_path') or os.getenv('ONTOS_DB_PATH') or _DEFAULT_DB
    return str(p)


def abox():
    """返回共享本体 ABox 适配层模块（ontos.abox_cost）。失败抛异常由调用方处理。"""
    _ensure_ontos_importable()
    from ontos import abox_cost
    return abox_cost


def project_read(project_id: str = None, limit: int = None) -> list:
    """项目档案（读本体 md_contract）：档案列 + 预算/成本 + 本体预警判定。

    ⚠ 只返回条目；需要 total/truncated 请用 project_portfolio。
    """
    return abox().project_facts(_abox_db_path(), contract_no=project_id or None,
                                limit=limit)


def project_portfolio(project_id: str = None, status: str = None,
                      limit: int = 20, offset: int = 0) -> dict:
    """项目组合查询：条目 + 全库总数/截断标记/全量预警分布（★防「把样本当全集」）。"""
    return abox().project_portfolio(_abox_db_path(), contract_no=project_id or None,
                                    status=status or None, limit=limit, offset=offset)


def cost_detail_page(project_id: str = None, limit: int = 20, offset: int = 0) -> dict:
    """成本明细（带 total/truncated 元信息）。"""
    return abox().project_cost_detail_page(_abox_db_path(), contract_no=project_id or None,
                                           limit=limit, offset=offset)


def cost_detail(project_id: str = None, limit: int = None) -> list:
    """成本明细（读本体 md_contract）：预算三分量 / 成本六分量 + 本体预警。"""
    return abox().project_cost_detail(_abox_db_path(), contract_no=project_id or None,
                                      limit=limit)


def not_available(domain: str) -> dict:
    """⌛未接入数据域的标准说明（红线：不得用演示数据冒充真实数据）。"""
    return abox().not_available(domain)


def read_entity(entity: str, filters: dict = None) -> dict:
    """本体 ABox 只读查询（供 ontology_read 原语）：按实体取真实事实。

    entity='Project'：contract_no 给定查单项目(project_read)，否则返回组合(project_portfolio)。
    其余实体暂未接入只读查询，提示改用 ontology_compute 调对应函数。
    """
    filters = filters or {}
    pid = filters.get('contract_no') or filters.get('project_id')
    if entity == 'Project':
        if pid:
            return {'success': True, 'entity': entity,
                    'result': project_read(pid, limit=filters.get('limit'))}
        return {'success': True, 'entity': entity,
                'result': project_portfolio(status=filters.get('status'),
                                            limit=int(filters.get('limit', 20) or 20))}
    return {'success': False, 'entity': entity, 'error': 'entity_read_not_supported',
            'message': f'实体 {entity} 的只读查询暂未接入；请用 ontology_compute 调用对应函数'}


def eval_action(action: str, project_id: str = None) -> dict:
    """本体动作护栏评估（供 ontology_act 原语）：只读校验是否可执行，不写库。

    基于 validate_project_action 评估当前事实(ABox)下动作的前置条件/不变量，
    返回 (executable, reasons)。确需执行须人工/流程确认。
    """
    db_path = _abox_db_path({})
    if not os.path.exists(db_path):
        return {'success': False, 'error': 'abox_db_not_found',
                'message': f'业务库不存在：{db_path}'}
    _ensure_ontos_importable()
    from ontos import domain_business as biz
    facts: dict = {}
    if project_id:
        rows = abox().project_facts(db_path, contract_no=project_id, limit=1)
        if rows:
            facts = rows[0]
    ok, reasons = biz.validate_project_action(action, facts)
    return {'success': True, 'action': action, 'executable': ok, 'reasons': reasons,
            'note': '仅护栏评估，未写库；确需执行需人工/流程确认'}


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
        if fn in ('cost_warning_portfolio', 'cost_warning_all'):
            result = abox_cost.cost_warning_portfolio(
                db_path, contract_no=params.get('contract_no') or None)
            return {'success': True, 'function': 'cost_warning_portfolio', 'result': result}
        if fn == 'project_facts':
            result = abox_cost.project_facts(
                db_path, contract_no=params.get('contract_no') or None,
                limit=params.get('limit'))
            return {'success': True, 'function': 'project_facts', 'result': result}
        if fn == 'project_portfolio':
            result = abox_cost.project_portfolio(
                db_path, contract_no=params.get('contract_no') or None,
                status=params.get('status') or None,
                limit=params.get('limit', 20), offset=params.get('offset', 0))
            return {'success': True, 'function': 'project_portfolio', 'result': result}
        if fn == 'cost_detail':
            result = abox_cost.project_cost_detail(
                db_path, contract_no=params.get('contract_no') or None,
                limit=params.get('limit'))
            return {'success': True, 'function': 'cost_detail', 'result': result}
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

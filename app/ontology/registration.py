# -*- coding: utf-8 -*-
"""emp-009 数字员工 + skill-ont-proc-inquiry 注册（幂等）。
与现轨 emp-008 / skill-proc-mail-inquiry 完全独立，不触碰其三。
"""
from datetime import datetime

from app.db.employees import db_upsert_skill, db_upsert_employee

_EMP_ID = "emp-009"
_SKILL_ID = "skill-ont-proc-inquiry"

_EMP_PROMPT = (
    "你是备件询价本体化智能体 emp-009（本体轨 NO-012）。你在「实体 + 知识/规则 + 动作注册表」之上进行 LLM 自主决策：\n"
    "① 读当前任务事实（状态/报价/审批/运单），② 从 allowed_actions 中选一个动作，"
    "③ 动作必须先通过规则校验引擎（前置条件/不变量），不满足则返回原因重新选择，"
    "④ 确定部署走存储/邮件网关执行为（Stage A 仅只读对照）。\n"
    "确定性能力（时长换算、最低价计算、邮件网关、持久化）由 tool/代码处理，你不替代。\n"
    "红线：绝不修改现轨 spare_mail_task / emp-008 / skill-proc-mail-inquiry。"
)


def register_emp009():
    db_upsert_skill({
        "id": _SKILL_ID,
        "name": "本体化备件询价决策",
        "desc": "本体轨（NO-012）：实体+规则+动作注册表，LLM 在规则约束内自主决策备件询价下一步",
        "category": "custom",
        "tags": ["采购", "本体", "LLM决策", "emp-009"],
        "enabled": True,
        "prompt": _EMP_PROMPT,
        "flow": "读事实→选动作→规则校验→执行/对照→审计；改规则不改代码",
        "skill_type": "ontology",
        "group": "备件询价(本体)",
    }, tools=[])

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db_upsert_employee({
        "id": _EMP_ID,
        "name": "备件询价智能体（本体化）",
        "desc": "本体轨（NO-012）备件询价：基于实体+知识规则+动作注册表，由 LLM 在规则约束内自主决策；独立于现轨 emp-008，零影响。",
        "type": "采购询比价(本体)",
        "created": ts,
        "updated": ts,
        "rag_kb": "",
        "prompt": _EMP_PROMPT,
        "model": "deepseek-v4",
        "skills": [_SKILL_ID],
        "enabled": True,
    })
    return {"employee": _EMP_ID, "skill": _SKILL_ID}


if __name__ == "__main__":
    print(register_emp009())
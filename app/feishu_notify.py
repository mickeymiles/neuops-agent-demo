# -*- coding: utf-8 -*-
"""飞书机器人告警通知（预留配置：webhook 从 settings 表读取）

支持自定义机器人 webhook + 可选加签(secret)。
未配置 webhook 时安全降级：仅记录日志，不发送。
"""
import base64
import hashlib
import hmac
import json
import logging
import time

import requests

from . import db

logger = logging.getLogger(__name__)


def _get_webhook_config() -> tuple:
    """从 settings 表读取飞书配置"""
    url = db.db_get_setting("feishu_webhook", "").strip()
    secret = db.db_get_setting("feishu_secret", "").strip()
    return url, secret


def _sign(secret: str, ts: int) -> str:
    """飞书自定义机器人加签：Base64(HMAC-SHA256(timestamp\nsecret))"""
    if not secret:
        return ""
    s = f"{ts}\n{secret}"
    h = hmac.new(secret.encode("utf-8"), s.encode("utf-8"), digestmod=hashlib.sha256).digest()
    return base64.b64encode(h).decode("utf-8")


def send_alert(severity: str, title: str, content: str, extras: dict = None) -> dict:
    """发送告警通知到飞书，返回 {"ok": bool, "msg": str}。

    severity: warning/critical
    title: 标题
    content: 正文
    extras: 可选 {entity_name, metric, value, threshold}
    """
    url, secret = _get_webhook_config()
    if not url:
        logger.info("[feishu] webhook not configured, skip. %s", title)
        return {"ok": True, "skipped": True, "msg": "webhook not configured"}

    ts = int(time.time())
    body = {
        "msg_type": "interactive",
        "timestamp": str(ts),
        "sign": _sign(secret, ts),
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"🚨 {title}"},
                "template": "red" if severity == "critical" else "orange"
            },
            "elements": [
                {"tag": "div", "text": {"tag": "plain_text", "content": content}},
                {"tag": "hr"},
                {"tag": "note", "elements": [{"tag": "plain_text", "content": f"NeuOps · {time.strftime('%Y-%m-%d %H:%M:%S')}"}]}
            ]
        }
    }
    if extras:
        lines = []
        for k, v in (extras or {}).items():
            lines.append(f"{k}: {v}")
        if lines:
            body["card"]["elements"].insert(1, {
                "tag": "div", "fields": [
                    {"is_short": True, "text": {"tag": "plain_text", "content": line}}
                    for line in lines[:4]
                ]
            })
    try:
        resp = requests.post(url, json=body, timeout=10)
        data = resp.json()
        if data.get("code") == 0:
            logger.info("[feishu] sent ok: %s", title)
            return {"ok": True, "msg": "sent"}
        logger.warning("[feishu] send failed: %s", data)
        return {"ok": False, "msg": str(data)}
    except Exception as e:  # noqa: BLE001
        logger.exception("[feishu] send exception")
        return {"ok": False, "msg": str(e)}


def notify_incident(incident: dict) -> dict:
    """自愈事件状态变化时通知飞书"""
    sev = "critical" if incident.get("severity") == "critical" else "warning"
    title = f"自愈事件 [{incident.get('state', '')}] {incident.get('rule_name', '')}"
    content = (f"实体: {incident.get('entity_type', '')} / {incident.get('entity_name', '')}\n"
               f"消息: {incident.get('message', '')}\n"
               f"修复动作: {incident.get('fix_action') or '待执行'}\n"
               f"重试: {incident.get('retry_count', 0)}")
    return send_alert(sev, title, content, {
        "rule": incident.get("rule_name", ""),
        "entity": incident.get("entity_name", ""),
        "state": incident.get("state", ""),
    })

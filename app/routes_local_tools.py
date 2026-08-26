"""
NeuOps 本地 Python MCP Tool HTTP 网关（/local/tools/*）
把 mcp_tools.py 中的 邮件/飞书/表 CRUD/采购解析 11 个工具，以 /local/tools/{tool_id} 的形式
暴露为独立 HTTP 接口，既可以被 neuops 本地 Skill 通过 MCP Gateway 复用，也能被其他外部 skill
直接通过 HTTP 调用。

工具 id 与 seed_data.MCP_TOOL_SEED 中 /local/tools 路径完全对应：
  邮件(3): send_mail / batch_send_mail / read_inbox_mail
  飞书(2): send_feishu_message / send_feishu_card
  表 CRUD(4): table_query / table_insert / table_update / table_upsert
  业务解析(2): procurement_parse_quote / procurement_parse_logistics
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from . import mcp_tools as _mt


router = APIRouter(prefix="/local/tools", tags=["local-mcp-tools"])


# =============== LLM 调用参数归一化（LLM 常把 dict/list 序列化成 JSON 字符串，此处自动剥壳）===============
import json as _json


def _coerce_dict(v: Any) -> Any:
    """dict 字段：如果 LLM 传了 JSON 字符串，自动解析；dict 原样返回；其他无效值抛错。"""
    if v is None:
        return None
    if isinstance(v, dict):
        return v
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        try:
            parsed = _json.loads(s)
        except _json.JSONDecodeError as e:
            raise ValueError(f"JSON 字符串解析失败: {e}（原始内容前80字：{s[:80]!r}）")
        if not isinstance(parsed, dict):
            raise ValueError(f"期望 JSON 对象(dict)，但解析后得到 {type(parsed).__name__}: {str(parsed)[:80]!r}")
        return parsed
    raise ValueError(f"期望 dict 或 JSON 字符串，实际 {type(v).__name__}")


def _coerce_list(v: Any) -> Any:
    """list 字段：兼容 JSON 字符串、逗号分隔字符串、单个元素。"""
    if v is None:
        return None
    if isinstance(v, list):
        return v
    if isinstance(v, tuple):
        return list(v)
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return []
        # 先尝试 JSON 解析（支持 ["a","b"] 风格）
        if s.startswith("[") or s.startswith('"'):
            try:
                parsed = _json.loads(s)
                if isinstance(parsed, list):
                    return parsed
                if isinstance(parsed, str):
                    return [parsed]
            except _json.JSONDecodeError:
                pass
        # 回退：逗号/分号分隔
        for sep in [",", ";", "，", "；"]:
            if sep in s:
                return [x.strip() for x in s.split(sep) if x.strip()]
        return [s]
    # 单个非字符串元素（如整数）包装成 list
    return [v]


# =============== 请求模型（保持与 seed_data.params_schema 对齐，LLM传字符串也能自适应）===============
class SendMailReq(BaseModel):
    to: List[str]
    subject: str
    body_text: str
    cc: Optional[List[str]] = None
    reply_to_message_id: Optional[str] = None

    @field_validator("to", "cc", mode="before")
    @classmethod
    def _list_fields(cls, v):
        return _coerce_list(v)


class BatchSendMailReq(BaseModel):
    receiver_email_list: List[str]
    subject: str
    body_text: str
    cc: Optional[List[str]] = None

    @field_validator("receiver_email_list", "cc", mode="before")
    @classmethod
    def _list_fields(cls, v):
        return _coerce_list(v)


class ReadInboxMailReq(BaseModel):
    since_timestamp: int
    filter_sender_email_list: Optional[List[str]] = None

    @field_validator("filter_sender_email_list", mode="before")
    @classmethod
    def _list_fields(cls, v):
        return _coerce_list(v)


class SendFeishuMessageReq(BaseModel):
    receiver_feishu_open_id: str
    content: str
    is_alert: bool = False


class SendFeishuCardReq(BaseModel):
    receiver_feishu_open_id: str
    card: Dict[str, Any]

    @field_validator("card", mode="before")
    @classmethod
    def _dict_field(cls, v):
        return _coerce_dict(v)


class TableQueryReq(BaseModel):
    table_key: str
    filters: Optional[Dict[str, Any]] = Field(default=None, alias="filters")
    limit: int = 100
    keyword: Optional[str] = ""  # 关键字模糊搜索（新增强）
    keyword_fields: Optional[List[str]] = None  # 指定搜索列（新增强）

    @field_validator("filters", mode="before")
    @classmethod
    def _dict_field(cls, v):
        return _coerce_dict(v)


class TableInsertReq(BaseModel):
    table_key: str
    record_id: Optional[str] = None
    data: Dict[str, Any]

    @field_validator("data", mode="before")
    @classmethod
    def _dict_field(cls, v):
        return _coerce_dict(v)


class TableUpdateReq(BaseModel):
    table_key: str
    record_id: str
    data: Dict[str, Any]

    @field_validator("data", mode="before")
    @classmethod
    def _dict_field(cls, v):
        return _coerce_dict(v)


class TableUpsertReq(BaseModel):
    table_key: str
    record_id: str
    data: Dict[str, Any]

    @field_validator("data", mode="before")
    @classmethod
    def _dict_field(cls, v):
        return _coerce_dict(v)


class ProcParseQuoteReq(BaseModel):
    body: str
    expected_qty: Optional[int] = None
    spare_part_model: str = ""


class ProcParseLogisticsReq(BaseModel):
    body: str


class ProcurementCreateTaskReq(BaseModel):
    """采购询比价任务创建（对话入口专用），参数对齐 9006 /api/procurement/tasks/agent"""
    project_id: str = ""
    project_name: str = ""
    contract_no: str = ""
    spare_part_model: str
    purchase_qty: float
    emergency_level: str
    inquiry_supplier_list: Optional[List[Any]] = None  # 可选：None=自动带全量资源池
    creator: str = "agent"

    @field_validator("inquiry_supplier_list", mode="before")
    @classmethod
    def _supplier_list(cls, v):
        if v is None or v == "" or v == []:
            return None
        if isinstance(v, str) and not v.strip():
            return None
        parsed = _coerce_list(v)
        # 列表中的 dict 项也要兼容 JSON 字符串
        result = []
        for item in parsed:
            if isinstance(item, dict):
                result.append(item)
            elif isinstance(item, str):
                try:
                    result.append(_coerce_dict(item))
                except Exception:
                    # 兜底：如果不是 JSON，保留字符串（会被 9006 校验拒绝）
                    result.append(item)
            else:
                result.append(item)
        return result if result else None


# =============== 工具执行辅助：统一异常处理 ===============
def _wrap(fn, **kwargs):
    try:
        return fn(**kwargs)
    except TypeError as e:
        raise HTTPException(status_code=400, detail=f"参数不正确: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


# =============== 3 个邮件工具 ===============
@router.post("/send_mail")
def local_tool_send_mail(req: SendMailReq):
    return _wrap(_mt.tool_send_mail, to=req.to, subject=req.subject, body_text=req.body_text,
                 cc=req.cc, reply_to_message_id=req.reply_to_message_id)


@router.post("/batch_send_mail")
def local_tool_batch_send_mail(req: BatchSendMailReq):
    return _wrap(_mt.tool_batch_send_mail, receiver_email_list=req.receiver_email_list,
                 subject=req.subject, body_text=req.body_text, cc=req.cc)


@router.post("/read_inbox_mail")
def local_tool_read_inbox_mail(req: ReadInboxMailReq):
    return _wrap(_mt.tool_read_inbox_mail, since_timestamp=req.since_timestamp,
                 filter_sender_email_list=req.filter_sender_email_list)


# =============== 2 个飞书工具 ===============
@router.post("/send_feishu_message")
def local_tool_send_feishu_message(req: SendFeishuMessageReq):
    return _wrap(_mt.tool_send_feishu_message,
                 receiver_feishu_open_id=req.receiver_feishu_open_id,
                 content=req.content, is_alert=req.is_alert)


@router.post("/send_feishu_card")
def local_tool_send_feishu_card(req: SendFeishuCardReq):
    return _wrap(_mt.tool_send_feishu_card,
                 receiver_feishu_open_id=req.receiver_feishu_open_id,
                 card=req.card)


# =============== 4 个表 CRUD 工具 ===============
@router.post("/table_query")
def local_tool_table_query(req: TableQueryReq):
    return _wrap(_mt.tool_table_query, table_key=req.table_key,
                 filter=req.filters, page_size=req.limit,
                 keyword=req.keyword or "", keyword_fields=req.keyword_fields)


@router.post("/table_insert")
def local_tool_table_insert(req: TableInsertReq):
    data = dict(req.data)
    if req.record_id is not None:
        # 若调用方提供 record_id，尝试写入主键列（按表推断主键名）
        tname = _mt._PROC_TABLE_MAP.get(req.table_key, req.table_key)
        pk = _mt._pick_pk(tname)
        data[pk] = req.record_id
    return _wrap(_mt.tool_table_insert, table_key=req.table_key, data=data)


@router.post("/table_update")
def local_tool_table_update(req: TableUpdateReq):
    return _wrap(_mt.tool_table_update, table_key=req.table_key,
                 record_id=req.record_id, data=req.data)


@router.post("/table_upsert")
def local_tool_table_upsert(req: TableUpsertReq):
    return _wrap(_mt.tool_table_upsert, table_key=req.table_key,
                 record_id=req.record_id, data=req.data)


# =============== 2 个业务解析工具 ===============
@router.post("/procurement_parse_quote")
def local_tool_proc_parse_quote(req: ProcParseQuoteReq):
    return _wrap(_mt.tool_procurement_parse_quote, body=req.body,
                 expected_qty=req.expected_qty, spare_part_model=req.spare_part_model)


@router.post("/procurement_parse_logistics")
def local_tool_proc_parse_logistics(req: ProcParseLogisticsReq):
    return _wrap(_mt.tool_procurement_parse_logistics, body=req.body)


# =============== 1 个采购业务动作 ===============
@router.post("/procurement_create_task")
def local_tool_proc_create_task(req: ProcurementCreateTaskReq):
    """创建询比价采购任务（对话入口专用），走 9006 标准流程，返回 task_id + 完整 task 对象。"""
    return _wrap(
        _mt.tool_procurement_create_task,
        project_id=req.project_id, project_name=req.project_name,
        contract_no=req.contract_no, spare_part_model=req.spare_part_model,
        purchase_qty=req.purchase_qty, emergency_level=req.emergency_level,
        inquiry_supplier_list=req.inquiry_supplier_list, creator=req.creator,
    )


# =============== 3 个对话辅助查询工具 ===============
class ProcQueryContractReq(BaseModel):
    keyword: str = ""


class ProcQuerySparePartReq(BaseModel):
    keyword: str = ""


class ProcQuerySupplierReq(BaseModel):
    keyword: str = ""


@router.post("/procurement_query_contract")
def local_tool_query_contract(req: ProcQueryContractReq):
    return _wrap(_mt.tool_procurement_query_contract, keyword=req.keyword or "")


@router.post("/procurement_query_spare_part")
def local_tool_query_spare_part(req: ProcQuerySparePartReq):
    return _wrap(_mt.tool_procurement_query_spare_part, keyword=req.keyword or "")


@router.post("/procurement_query_supplier")
def local_tool_query_supplier(req: ProcQuerySupplierReq):
    return _wrap(_mt.tool_procurement_query_supplier, keyword=req.keyword or "")

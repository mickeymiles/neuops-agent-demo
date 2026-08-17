# -*- coding: utf-8 -*-
"""SQLite 数据层包：按表域拆分后的统一出口。

对外导入保持兼容：
    from app import db            # db.init_session_db() 等
    from . import db              # app 内部模块既有写法
    from app.db import x          # 或 from .db import x
"""

from .base import (
    _db_lock,
    _get_conn,
    _ensure_column,
    _COST_INPUT_PER_M,
    _COST_OUTPUT_PER_M,
    _query_rows,
    _query_one,
    _est_tokens,
    _text_summary,
    _agent_name_map,
    _parse_route,
)

from .schema import (
    init_session_db,
    init_config_db,
)

from .sessions import (
    ensure_conversation,
    save_user_message,
    save_agent_message,
    list_conversations,
    db_create_project,
    db_list_projects,
    db_rename_project,
    db_delete_project,
    db_update_conversation,
    db_delete_conversation,
    db_get_deleted_mock_convs,
    db_mark_mock_conv_deleted,
    db_share_conversation,
    db_get_conversation_share,
    db_get_conv_by_share,
    get_conversation_messages,
    _load_chat_history,
    seed_mock_conversations,
)

from .seed import (
    seed_config_db,
    sync_seed_employees,
    ensure_mcp_server_mapping,
    db_list_mcp_servers,
    db_get_mcp_server,
    db_upsert_mcp_server,
    db_delete_mcp_server,
    db_sync_server_tools,
    db_list_mcp_tools,
    db_get_mcp_tool,
    db_update_mcp_tool,
)

from .employees import (
    db_list_employees,
    db_get_employee,
    db_upsert_employee,
    db_delete_employee,
    db_set_employee_skill_enabled,
    db_link_employee_skills,
    db_unlink_employee_skill,
    db_list_skills,
    db_get_skill,
    db_set_skill_enabled,
    db_upsert_skill,
    db_delete_skill,
    db_set_employee_enabled,
)

from .tasks import (
    db_list_long_tasks,
    db_get_long_task,
    db_create_long_task,
    db_update_long_task,
    db_delete_long_task,
    db_list_todos,
    db_list_todo_history,
    db_list_bg_tasks,
)

from .kb import (
    db_list_knowledge_bases,
    db_get_knowledge_base,
    db_create_knowledge_base,
    db_rename_knowledge_base,
    db_delete_knowledge_base,
    db_update_kb_stats,
    db_add_kb_chunks,
    db_clear_kb_chunks,
    db_list_kb_chunks,
    db_count_kb_chunks,
    db_delete_kb_chunk,
    db_get_kb_chunk,
    db_bind_employee_kb,
    db_get_employee_kb_ids,
    db_get_employee_kb_names,
    db_get_kb_employees,
)

from .ops import (
    OPS_ENTITY_TYPES,
    init_ops_db,
    db_get_setting,
    db_set_setting,
    db_get_settings_all,
    ops_save_metric,
    ops_save_metrics,
    ops_get_metrics,
    ops_get_latest_value,
    ops_get_latest_snapshot,
    ops_cleanup_old_metrics,
    ops_save_logs,
    ops_get_logs,
    ops_count_logs,
    ops_cleanup_old_logs,
    ops_upsert_entity,
    ops_save_entities,
    ops_get_entities,
    ops_get_entity,
    ops_save_relations,
    ops_get_relations,
)

from .bidding import (
    BID_STATUS_FLOW,
    PARSE_SECTIONS,
    init_bid_db,
    bid_create_project,
    bid_list_projects,
    bid_get_project,
    bid_update_project,
    bid_delete_project,
    bid_set_status,
    bid_save_parse_report,
    bid_add_generated_doc,
    bid_save_check_result,
)

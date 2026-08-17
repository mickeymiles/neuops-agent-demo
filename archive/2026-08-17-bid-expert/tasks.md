# Tasks：NO-009 投标业务专家能力

> 变更：`20260817-bid-expert` | 状态：已完成

## A. 工作台 + 拆标

- [x] T1 变更提案 + NO-009 delta specs + design + tasks（本目录）
- [x] T2 `bid_projects` 数据模型（含拆标报告/成果 JSON 字段）— `app/db/bidding.py`
- [x] T3 拆标引擎：正则粗筛章节切分 → 分块喂 DeepSeek 按 JSON Schema 提炼 — `app/bidding/bid_engine.py`
- [x] T4 项目 CRUD + 上传(文本抽取) + 拆标 + 生成 + 自检 + 导出 API — `app/bidding/routes_bidding.py`
- [x] T5 工作台页面：项目列表 → 详情（上传区/拆标报告/生成面板/自检/导出）— `static/bidding.html`
- [x] T6 挂载路由 + 侧边栏入口 + uploads/bid 目录 — `main.py`、`static/index.html`

## B. 聊天联动

- [x] T7 emp-007 `open_url` 指向 /bidding — `app/agent_chat.py`
- [x] T8 emp-007 prompt 追加"信息问答 vs 跳转工作台"行为指引 — `app/agent_chat.py`

## C. 知识库

- [x] T9 预置 5 类空库（资质/业绩/素材/模板/人员）— `seed_bid_kb.py`
- [x] T10 每类 1–2 条示例数据写入 Chroma — `seed_bid_kb.py` 幂等向量化
- [x] T11 5 库绑定 emp-007（替换现有单一绑定）— `seed_bid_kb.py` → Chroma 绑定

## D. 测试归档

- [x] T12 pytest 用例（标注 `# NO-009 FR-x`）— `tests/test_bid.py`
- [x] T13 更新 TRACEABILITY / specs README 索引，归档 — `specs/`、`archive/`

## 验收

- [x] `cd neuops-agent-demo && pytest -q` 全量通过（58 passed，1 例既有环境失败与本次无关）
- [x] `/bidding` 可访问，完整链路可跑通
- [x] 聊天 emp-007 重操作跳转、信息问答留聊天
- [x] 5 类知识库预置并绑定 emp-007

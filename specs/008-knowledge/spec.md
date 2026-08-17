# 知识库与 RAG Specification

> 规格编号: NO-008 | 状态: 生效 | 最后更新: 2026-08-17
> 对应代码: `app/knowledge.py`

## Purpose

提供知识文档入库、向量化检索与 RAG 问答能力：解析多格式文档（xlsx/pdf/docx）并分块向量化（Chroma + fastembed），为 Agent 对话提供知识增强；在向量组件不可用时降级为关键词检索，保证能力可用。

## Requirements

### Requirement: 知识入库

系统 SHALL 支持将知识文档（xlsx、pdf、docx）解析后按固定分块策略（CHUNK_SIZE=400、CHUNK_OVERLAP=50）切分为知识块，写入向量库并建立标题索引。

#### Scenario: 入库分块

- GIVEN 上传一份 1200 字的文档
- WHEN 执行入库
- THEN 按 400 字块重叠 50 字切分产生多个知识块并入库

### Requirement: 向量检索

系统 SHALL 支持语义向量检索：将查询向量化（默认 BAAI/bge-small-zh-v1.5 模型），在向量库中检索 Top-K 相似知识块（默认 DEFAULT_TOP_K=5）。

#### Scenario: 语义检索

- GIVEN 查询"如何排查数据库连接数过高"
- WHEN 执行检索
- THEN 返回语义最相关的 Top-5 知识块

### Requirement: 降级检索

系统 SHALL 在 Chroma/fastembed 不可用时降级为 SQLite 关键词检索，保证 RAG 能力可用，并记录降级状态。

#### Scenario: 组件不可用

- GIVEN 向量组件初始化失败
- WHEN 执行检索
- THEN 使用关键词匹配返回结果，能力不中断

### Requirement: 模型加载容错

系统 SHALL 在模型加载失败（如网络不可达）时给出明确错误与可用提示，并通过镜像端点（HF_ENDPOINT）加载模型，不阻塞系统启动。

#### Scenario: 加载失败提示

- GIVEN 无法访问 HuggingFace
- WHEN 加载嵌入模型
- THEN 返回可读错误，系统其余功能正常运行

### Requirement: 检索接入对话

系统 SHALL 将知识检索结果作为上下文注入 Agent 对话（search_knowledge），提升问答准确性。

#### Scenario: 对话增强

- GIVEN 用户询问知识库中的运维操作问题
- WHEN Agent 回答前检索知识
- THEN 回答引用相关知识块内容

## 非功能需求

- NFR-1：单次检索 SHALL 在 2 秒内返回
- NFR-2：入库失败 SHALL 不影响已存在知识内容

## 测试标准

- TC-1：入库分块与检索用例（对应 FR-1~FR-2），位置 `tests/test_knowledge.py`
- TC-2：降级检索用例（对应 FR-3）

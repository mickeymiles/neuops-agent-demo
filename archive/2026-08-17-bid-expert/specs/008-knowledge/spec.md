# Delta Spec：NO-008 知识库与 RAG（投标知识库预置与绑定）

> 本 delta 追加一条 Requirement：预置 5 类投标知识库并绑定 emp-007。

## ADDED Requirements

### Requirement: 投标知识库预置与绑定

系统 SHALL 预置 5 类投标知识库：资质库、业绩库、素材库、模板库、人员库；每类 SHALL 预置 1–2 条示例数据（写入 Chroma）；系统 SHALL 将这 5 类库绑定到售前投标专家（emp-007），使其检索范围覆盖上述知识库。

#### Scenario: 预置与绑定

- GIVEN 系统初始化完成
- WHEN 查询知识库列表
- THEN 可见 5 类投标知识库（每类含 1–2 条示例数据），且 emp-007 的绑定知识库包含这 5 类

## MODIFIED Requirements

无。

## REMOVED Requirements

无。

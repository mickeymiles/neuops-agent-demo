# Delta Spec：NO-008 知识库与 RAG（测试覆盖）

> 本 delta 不修改任何既有 Requirement，仅新增测试标准（TC）与测试位置声明。

## ADDED Requirements

### Requirement: 知识库测试覆盖

系统 SHALL 为知识库与 RAG 提供单元测试，覆盖：文档解析（txt/md/xlsx）、
切块（聚合/定长/重叠/碎片过滤）、中文分词、关键词降级检索与空输入处理。

#### Scenario: 知识库测试全绿

- GIVEN 测试环境（无真实向量库/Embedding 服务）
- WHEN 运行 `python3 -m pytest tests/test_knowledge.py -q`
- THEN 全部用例离线通过，且测试数据（kb-test-*）测后清理不留脏数据

## MODIFIED Requirements

无。

## REMOVED Requirements

无。

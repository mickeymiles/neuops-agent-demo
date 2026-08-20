# 数字员工工作台 Specification（delta 增量）

> 变更编号：`20260820-employee-workbench` | 类型：delta | 目标主规格：`specs/010-employee-workbench/spec.md`

## ADDED Requirements

### Requirement: FR-1 数字员工工作台入口

系统 SHALL 在数字员工详情的首个 Tab 提供工作台，并根据当前员工的业务类型或专属配置展示差异化内容。

#### Scenario: 默认工作台

- GIVEN 数字员工没有保存专属工作台配置
- WHEN 用户打开该员工详情
- THEN 系统展示与该员工业务类型匹配的默认工作台

#### Scenario: 员工配置隔离

- GIVEN 两个数字员工保存了不同工作台配置
- WHEN 用户分别打开两个员工详情
- THEN 系统分别展示各自配置且互不影响

### Requirement: FR-2 工作台配置契约

系统 SHALL 以持久化的受约束 JSON 契约管理工作台，并 SHALL 拒绝非白名单组件、超限结构和无效字段类型。

#### Scenario: 保存合法配置

- GIVEN 用户提交合法的工作台配置
- WHEN 服务端处理员工 PATCH 请求
- THEN 配置被持久化且后续完整员工查询返回同一配置

#### Scenario: 拒绝非法配置

- GIVEN 配置包含非白名单组件或结构不符合约束
- WHEN 用户提交配置
- THEN 服务端返回 400 且原配置不变

#### Scenario: 恢复默认

- GIVEN 员工已有专属工作台配置
- WHEN 用户执行恢复默认
- THEN 系统清除专属配置并按员工业务类型返回默认工作台

### Requirement: FR-3 经营业务系统内嵌

系统 SHALL 在经营分析员工的工作台内直接嵌入 contract 业务页面，且 SHALL 仅使用平台配置的业务系统地址。

#### Scenario: 工作台内访问业务页面

- GIVEN contract 业务系统地址已配置且允许同源平台嵌入
- WHEN 用户打开经营分析员工的工作台
- THEN contract 页面在当前工作台内显示且无需打开新窗口

#### Scenario: 拒绝任意外站地址

- GIVEN 用户在工作台 JSON 中为业务系统组件提交自定义 URL
- WHEN 服务端校验工作台配置
- THEN 服务端返回 400 且不保存该配置

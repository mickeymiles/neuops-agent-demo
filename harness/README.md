# Harness CI/CD 预留配置（注册后激活）

本目录为 **Harness 云版流水线模板**，用于把 DevOps 闭环（CI 构建 + CD 部署）接入 Harness。
当前 Harness 账号尚未注册，配置已就绪，注册后按下方步骤填入账号/密钥即可激活。

## 闭环架构

```
Git push → Harness CI(静态检查+单测+镜像构建) → Harness CD(SSH 部署+健康检查+失败自动回滚)
         → 监控(统一探针) → 告警(飞书) → 自愈(全自动) → 修复验证 → 事件闭环
```

## 激活步骤（预计 20 分钟）

1. **注册 Harness 云版**（免费档）：https://app.harness.io → Sign up → 选 CI/CD Module
2. **创建项目**：名称 `neuops`，组织 `devops`
3. **连接 Git 仓库**：按向导把 GitHub 私有仓库 `neuops-agent-demo` 接入
4. **配置 Secrets**（项目 → 治理 → 密文）：
   | Secret | 值 | 用途 |
   |---|---|---|
   | `github_token` | GitHub PAT（repo 权限） | CI 拉取代码 |
   | `docker_registry` | 如 `ghcr.io/<owner>/neuops-agent-demo` | 镜像仓库 |
   | `docker_username` / `docker_password` | 镜像仓库账号 | 推送镜像 |
   | `ssh_user` | 如 `ubuntu` | CD SSH 部署 |
   | `ssh_host` | 服务器 IP | CD SSH 部署 |
   | `ssh_key` | 服务器 SSH 私钥 | CD SSH 部署 |
5. **导入流水线**：Pipelines → 新建 → 导入 YAML → 上传 `ci-pipeline.yaml` / `cd-pipeline.yaml`
6. **触发**：连接 GitHub Webhook 后 push main 自动触发

## 模板说明

- `ci-pipeline.yaml`：lint(ruff) → test(pytest) → build docker 镜像 → push 镜像仓库
- `cd-pipeline.yaml`：SSH 到服务器 → 拉取最新镜像 → 重启容器 → 健康检查 → 失败自动回滚上一版本
- 均使用占位符 `$<+secrets.getValue("KEY")>` 读取 Harness 密文，无需硬编码

> 回滚机制：CD 中保存上一镜像 tag，健康检查连续失败 2 次自动 `docker compose down && 启动旧 tag`，并飞书通知。

## 备选方案

若暂不注册 Harness，`.github/workflows/ci.yml`（GitHub Actions）已提供真实 CI（lint+test+镜像构建）；
CD 可直接用 `scripts/deploy.sh` 手动触发或挂到 CI 的 `workflow_dispatch`。

# CI/CD 配置总览（GitHub Actions 真实闭环 + Harness 云版模板备选）

## 当前状态：GitHub Actions 已启用真实闭环

`.github/workflows/ci.yml` 已配置完整流水线，push 到 `main` 自动触发：

```
Git push (main) → CI.lint(ruff + pytest 34 项) → CI.docker-build(镜像→ghcr.io)
              → CI.deploy(SSH 同步代码 → 安装依赖 → 重启 neuops-9007 → 健康检查)
              → 监控(统一探针) → 告警(飞书) → 人工处置 → 事件闭环
```

### 本地手动部署（等价命令）

```bash
./scripts/deploy.sh ubuntu@122.51.98.98 /home/ubuntu/neuops-agent-demo
```

### GitHub Secrets 配置（仓库 → Settings → Secrets and variables → Actions）

| Secret | 值 | 用途 |
|---|---|---|
| `DEPLOY_SSH_KEY` | 服务器 SSH 私钥（用于 CI 部署，公钥已加入服务器 `~/.ssh/authorized_keys`） | CD rsync/ssh |
| `DEPLOY_HOST` | `122.51.98.98` | 服务器地址 |
| `DEPLOY_USER` | `ubuntu` | SSH 用户 |
| `DEPLOY_PATH` | `/home/ubuntu/neuops-agent-demo` | 部署目录 |

> 服务器端执行逻辑见 `scripts/remote_deploy.sh`（装依赖 → `systemctl restart neuops-9007` → 健康检查）。

## 备选：Harness 云版（未激活，模板保留）

以下 `ci-pipeline.yaml` / `cd-pipeline.yaml` 为 Harness 云版流水线模板，适合后续接入 Harness 统一管理。激活步骤（预计 20 分钟）：

1. **注册 Harness 云版**（免费档）：https://app.harness.io → Sign up → 选 CI/CD Module
2. **创建项目**：名称 `neuops`，组织 `devops`
3. **连接 Git 仓库**：按向导把 GitHub 私有仓库 `neuops-agent-demo` 接入
4. **配置 Secrets**（项目 → 治理 → 密文）：
   | Secret | 值 | 用途 |
   |---|---|---|
   | `github_token` | GitHub PAT（repo 权限） | CI 拉取代码 |
   | `docker_registry` | 如 `ghcr.io/<owner>/neuops-agent-demo` | 镜像仓库 |
   | `docker_username` / `docker_password` | 镜像仓库账号 | 推送镜像 |
   | `ssh_user` / `ssh_host` | `ubuntu` / `122.51.98.98` | CD SSH 部署 |
   | `ssh_key` | 服务器 SSH 私钥 | CD SSH 部署 |
5. **导入流水线**：Pipelines → 新建 → 导入 YAML → 上传 `ci-pipeline.yaml` / `cd-pipeline.yaml`
6. **触发**：连接 GitHub Webhook 后 push main 自动触发

### 模板说明

- `ci-pipeline.yaml`：lint(ruff) → test(pytest) → build docker 镜像 → push 镜像仓库
- `cd-pipeline.yaml`：SSH 到服务器 → 拉取最新镜像 → 重启容器 → 健康检查 → 失败自动回滚上一版本
- 均使用占位符 `$<+secrets.getValue("KEY")>` 读取 Harness 密文，无需硬编码

> 回滚机制：CD 中保存上一镜像 tag，健康检查连续失败 2 次自动 `docker compose down && 启动旧 tag`，并飞书通知。

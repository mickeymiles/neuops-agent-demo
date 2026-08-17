# NeuOps 服务器版本存档指纹 20260816

> 本快照记录 2026-08-16 的部署状态；其中自愈（self-heal）/ 代码修复（code heal）相关文件与 incidents 数据已于 2026-08-17（变更 `20260817-remove-self-heal`）整体移除。

生成时间: 2026-08-16 09:44:52 CST
部署目录: /home/ubuntu/neuops-agent-demo
本地 git tag: v1.0-pre-dsh (HEAD=e133c525eaa8ae50937e84040fe2084d697ce4fb)

## 1. systemd 服务状态 neuops-9007
```
MainPID=2771158
ExecStart={ path=/home/ubuntu/recon/.venv/bin/python3 ; argv[]=/home/ubuntu/recon/.venv/bin/python3 -B -m uvicorn main:app --host 0.0.0.0 --port 9007 ; ignore_errors=no ; start_time=[Sun 2026-08-16 09:20:54 CST] ; stop_time=[n/a] ; pid=2771158 ; code=(null) ; status=0/0 }
ActiveState=active
SubState=running
```

## 2. 健康检查输出 GET http://127.0.0.1:9007/api/ops/overview
```json
{"ok":true,"updatedAt":"2026-08-16 09:44:52","probe":{"running":true,"lastRunAt":"2026-08-16 09:44:44","interval":30,"collectors":["server","container","database","middleware","application","network","log"],"lastError":""},"entities":{"total":10,"byType":{"server":3,"database":1,"network":3,"container":0,"middleware":0,"application":2},"byStatus":{"running":10,"degraded":0,"down":0,"unknown":0},"types":{"server":{"label":"服务器","color":"#4f8cff","icon":"server"},"database":{"label":"数据库","color":"#34d399","icon":"database"},"network":{"label":"网络","color":"#22d3ee","icon":"network"},"container":{"label":"容器","color":"#a78bfa","icon":"container"},"middleware":{"label":"中间件","color":"#fb923c","icon":"middleware"},"application":{"label":"应用","color":"#fbbf24","icon":"application"}}},"alerts":{"total":33,"firing":31},"incidents":{"total":5,"open":30,"recent":[{"id":"INC-36262EC4","alert_id":33,"rule_name":"应用健康检查失败","entity_type":"application","entity_name":"neuops-agent","severity":"critical","state":"repairing","message":"neuops-agent 健康检查失败，状态 degraded","fix_action":"restart_self","fix_log":"[2026-08-16 02:35:03] 执行动作 restart_self","retry_count":0,"created_at":"2026-08-16 02:35:03","updated_at":"2026-08-16 02:35:03","resolved_at":""},{"id":"INC-D7F236FA","alert_id":33,"rule_name":"应用健康检查失败","entity_type":"application","entity_name":"neuops-agent","severity":"critical","state":"recovered","message":"neuops-agent 健康检查失败，状态 degraded","fix_action":"restart_self","fix_log":"[2026-08-16 02:34:28] 执行动作 restart_self\n[2026-08-16 02:34:31] 动作结果 ok=True msg=restart neuops on port 9007\n[2026-08-16 02:34:31] 验证结果 resolved=True","retry_count":0,"created_at":"2026-08-16 02:34:28","updated_at":"2026-08-16 02:34:31","resolved_at":"2026-08-16 02:34:31"},{"id":"INC-07F27AD5","alert_id":32,"rule_name":"应用日志错误突增","entity_type":"log","entity_name":"log","severity":"warning","state":"manual","message":"无匹配修复方案，已升级人工","fix_action":"code_heal","fix_log":"[2026-08-15 13:06:37] 执行动作 code_heal\n[2026-08-15 13:06:37] [code-heal] 开始代码级自愈，repo=/home/ubuntu/neuops-agent-demo\n[2026-08-15 13:06:37] [code-heal] 诊断上下文 2928 字符\n[2026-08-15 13:06:37] [code-heal] 无匹配修复规则且未配置 LLM，升级人工（护栏：不猜测修复）\n[2026-08-15 13:06:37] 动作结果 ok=False msg=code_heal 结束，状态=manual\n[2026-08-15 13:06:37] 代码自愈已升级人工","retry_count":0,"created_at":"2026-08-15 13:06:37","updated_at":"2026-08-15 13:06:37","resolved_at":""},{"id":"INC-B7065D89","alert_id":31,"rule_name":"应用日志错误突增","entity_type":"log","entity_name":"log","severity":"warning","state":"manual","message":"无匹配修复方案，已升级人工","fix_action":"code_heal","fix_log":"[2026-08-15 13:05:37] 执行动作 code_heal\n[2026-08-15 13:05:37] [code-heal] 开始代码级自愈，repo=/home/ubuntu/neuops-agent-demo\n[2026-08-15 13:05:37] [code-heal] 诊断上下文 2928 字符\n[2026-08-15 13:05:37] [code-heal] 无匹配修复规则且未配置 LLM，升级人工（护栏：不猜测修复）\n[2026-08-15 13:05:37] 动作结果 ok=False msg=code_heal 结束，状态=manual\n[2026-08-15 13:05:37] 代码自愈已升级人工","retry_count":0,"created_at":"2026-08-15 13:05:37","updated_at":"2026-08-15 13:05:37","resolved_at":""},{"id":"INC-709B1151","alert_id":30,"rule_name":"应用日志错误突增","entity_type":"log","entity_name":"log","severity":"warning","state":"manual","message":"无匹配修复方案，已升级人工","fix_action":"code_heal","fix_log":"[2026-08-15 13:04:37] 执行动作 code_heal\n[2026-08-15 13:04:37] [code-heal] 开始代码级自愈，repo=/home/ubuntu/neuops-agent-demo\n[2026-08-15 13:04:37] [code-heal] 诊断上下文 2928 字符\n[2026-08-15 13:04:37] [code-heal] 无匹配修复规则且未配置 LLM，升级人工（护栏：不猜测修复）\n[2026-08-15 13:04:37] 动作结果 ok=False msg=code_heal 结束，状态=manual\n[2026-08-15 13:04:37] 代码自愈已升级人工","retry_count":0,"created_at":"2026-08-15 13:04:37","updated_at":"2026-08-15 13:04:37","resolved_at":""}]},"serverSnapshot":{"VM-0-12-ubuntu":{"cpu_percent":0.5,"cpu_core_count":4.0,"cpu_load_1m":0.0,"cpu_load_5m":0.02392578125,"cpu_load_15m":0.00390625,"mem_total_gb":3.635944366455078,"mem_used_gb":1.0329971313476562,"mem_available_gb":2.602947235107422,"mem_percent":28.4,"swap_percent":6.6,"swap_total_gb":1.9414024353027344,"disk_root_percent":75.8,"disk_root_used_gb":28.471981048583984,"disk_root_free_gb":9.073806762695312,"process_count":137.0,"process_running":0.0,"uptime_sec":6188193.0}}}
```

## 3. requirements.txt 全文
```
fastapi
uvicorn[standard]
httpx
python-multipart
openpyxl
pypdf
python-docx
chromadb
fastembed
psutil>=5.9.0
requests>=2.31.0
```

## 4. 关键文件 sha256
```
12e1c3bae82e7f3d5bbbafc9b557e4f5b6ffce90845b722e1741e66007e1eb4f  .gitignore
20cef27d679eb29f7590dd563d166f7c6ebdcee07eab3ddf2d6eb54dda0fd4ae  Dockerfile
c89eb484c88db17cc8ec4f3669e401aa3288535dbd791f5113a58e5472ef8244  README.md
ccc1121952dbb4f06daaf5959f840eeedffaf586b7222478537a0f1f479c2aa1  app/__init__.py
c75145084a98a0f12a897bb4bf5fc2be909c1252724d8f0bba6e10ee963784ed  app/agent_chat.py
844a3c9cbffabe786a4697be67c3080429a66ce3382c3c87817ce3040931dd0e  app/alert_engine.py
ac9401d679c62ce6b256c18a2a2d842435b45c38bd00634c94f4f9670775e53b  app/config.py
5e7bc56c525b8a701e3ea6cb8002b137f3f05de22f271c25b2ee6fc2dd34e653  app/db.py
098dab3d1b6a4d3c68eef091cf423622d56e6f07e6d84824337cef2cfdfd780f  app/devtools.py
ea775be3a11e4f55446a64fd628a5a4f64a01c5a3cbde507ef9729a75c6fb85b  app/feishu_notify.py
2cd797dbd2ae0b1c9756ffbd4aa92fe09305549c5ad5440599a1bd9ca1d49ae7  app/knowledge.py
125b56816699368c91c77841e62b23b2f30afad8303d8a24f39f7ae8ce1045c1  app/mcp_tools.py
56b6665f5250d0ba1997f749317142167eb547b5dea00f9cf0155fc80489a0e5  app/mock_data.py
5e4f17007bf181657cbc13f6203d60a07c534a73fbb02282f13a3a5927dfd060  app/ops_code_heal.py
6ba7763fb718420a8760160329707f876fa4ac884b83e9334e4a4b01ab8a1315  app/ops_ontology.py
2ab0a6dd14a8c9a1dfe37ee42334e982a71cf37e23aedecf25edc6bd76085b21  app/ops_self_heal.py
309969339ecae8703c3b35cfbf0ef03e908eeafd873297929ae5fed976c35315  app/routes_employees.py
99ba2ed9a2588dd6552794f8698fd6b4366a5edfe13a3f0032e299b3ba43daa1  app/routes_knowledge.py
b91a36f40d34069a82f43653b6c42507940976e5e397aa63cdfe621c985e986f  app/routes_manage.py
94432691588dca3b073119c61953881a6d1c02da82be28819ace0f482d0df08c  app/routes_monitor.py
fe04614021ee1d3be977b432d48de36baa1d6831a31a68f3ba5b7e2d3cdcc4e7  app/routes_ops.py
ed654964330a91a1dac9bfe76d7551d2458232384dea639546d4b6b6596aea7a  app/routes_tasks.py
b70d4e0bd2c4cff21b0d093b9db9659cd3e8fa4a9f2d479ebb4b0130eb97431b  app/routes_workspace.py
6d10a189e0952c86eb03372c07a7509b4709a6cc3acc657925af981c413b51c4  app/traditional_pages.py
11e7e50fa6807dcc6059cabb479e47bdf9bdbf9f80336ff000883abe92d70901  docker-compose.yml
8bc1bb86f8aa0449c7a0784bc82857a2053d0ff390b5dad5c166eac0eed6b178  main.py
1341d5d34bbd9092700743bdc3d95397a6aed8312a140d72ce35af372705eb9a  mcp_gateway.py
b4723a80e969c2f24f12782d604283d929e9b056bbbc02742fad9dc83459f546  mock_data.py
179d0425d42b556063e5b420e35b5da02892252bba6dd6ff52636cc8c7392f8f  requirements.txt
41233e5b678c0b3389f7e8f6274d2976cb07fb65818faee233b3d62c5ffd741e  scripts/deploy.sh
36cd513b4a9df8458a7bfe35c0d59ee4be0b3f10bdd1ed92f80b4a03350570e5  scripts/push_github.sh
6d061a5cc9205ddf7110ba8ce6c1cdc7b92c2ad21a016f1de76020d276973c2f  scripts/remote_deploy.sh
212439e317c0f0f1b320fa2aa8918f165bdd765c6127c30a0fabc4a1b39fff83  seed_data.py
a1d928a511f438993f04753221e0c52a9ae381754087edcfb69423829618abc0  static/index.html
```

## 5. 生产数据说明（不随代码备份，回退时保留）
```
-rw-r--r-- 1 ubuntu ubuntu 33169408 Aug 16 09:44 /home/ubuntu/neuops-agent-demo/neuops_sessions.db

/home/ubuntu/neuops-agent-demo/chroma_data:
total 42636
drwxr-xr-x  3 ubuntu ubuntu     4096 Aug 16 07:55 .
drwxr-xr-x 19 ubuntu ubuntu     4096 Aug 16 09:44 ..
-rw-r--r--  1 ubuntu ubuntu 43642880 Aug 16 07:55 chroma.sqlite3
drwxr-xr-x  2 ubuntu ubuntu     4096 Aug 15 01:43 d66a42a3-d2bc-4c10-842c-e8eb5acedcb6

/home/ubuntu/neuops-agent-demo/uploads:
total 8
drwxr-xr-x  2 ubuntu ubuntu 4096 Aug 15 08:58 .
drwxr-xr-x 19 ubuntu ubuntu 4096 Aug 16 09:44 ..
```

## 6. 备份包校验
备份包路径: /home/ubuntu/backup/neuops-agent-demo-20260816.tar.gz
备份包大小: 938226 bytes
备份包 sha256: eda6e8656641300aa9ce5cdc87d6cedfa32ddf9ee35d47c1a08ab18ee8c71119

## 7. 文件清单（备份包内）
```
neuops-agent-demo/
neuops-agent-demo/mcp_gateway.py
neuops-agent-demo/docs/
neuops-agent-demo/docs/WORKLOG.md
neuops-agent-demo/harness/
neuops-agent-demo/harness/ci-pipeline.yaml
neuops-agent-demo/harness/README.md
neuops-agent-demo/harness/cd-pipeline.yaml
neuops-agent-demo/scripts/
neuops-agent-demo/scripts/build_kb.py
neuops-agent-demo/scripts/push_github.sh
neuops-agent-demo/scripts/update_mock.py
neuops-agent-demo/scripts/split_refactor.py
neuops-agent-demo/scripts/remote_deploy.sh
neuops-agent-demo/scripts/init_ops.py
neuops-agent-demo/scripts/apply_groups.py
neuops-agent-demo/scripts/deploy.sh
neuops-agent-demo/tools-page.png
neuops-agent-demo/Dockerfile
neuops-agent-demo/main.py
neuops-agent-demo/seed_data.py
neuops-agent-demo/README.md
neuops-agent-demo/docker-compose.yml
neuops-agent-demo/app/
neuops-agent-demo/app/ops_self_heal.py
neuops-agent-demo/app/ops_code_heal.py
neuops-agent-demo/app/routes_ops.py
neuops-agent-demo/app/routes_knowledge.py
neuops-agent-demo/app/db.py
neuops-agent-demo/app/routes_workspace.py
neuops-agent-demo/app/routes_manage.py
neuops-agent-demo/app/knowledge.py
neuops-agent-demo/app/ops_ontology.py
neuops-agent-demo/app/routes_employees.py
neuops-agent-demo/app/routes_monitor.py
neuops-agent-demo/app/traditional_pages.py
neuops-agent-demo/app/probe/
neuops-agent-demo/app/probe/cli.py
neuops-agent-demo/app/probe/manager.py
neuops-agent-demo/app/probe/server_collector.py
neuops-agent-demo/app/probe/container_collector.py
neuops-agent-demo/app/probe/database_collector.py
neuops-agent-demo/app/probe/application_collector.py
neuops-agent-demo/app/probe/__init__.py
neuops-agent-demo/app/probe/log_collector.py
neuops-agent-demo/app/probe/base.py
neuops-agent-demo/app/probe/network_collector.py
neuops-agent-demo/app/probe/middleware_collector.py
neuops-agent-demo/app/mcp_tools.py
neuops-agent-demo/app/mock_data.py
neuops-agent-demo/app/agent_chat.py
neuops-agent-demo/app/__init__.py
neuops-agent-demo/app/devtools.py
neuops-agent-demo/app/config.py
neuops-agent-demo/app/feishu_notify.py
neuops-agent-demo/app/routes_tasks.py
neuops-agent-demo/app/alert_engine.py
neuops-agent-demo/static/
neuops-agent-demo/static/manage.css
neuops-agent-demo/static/knowledge.html
... (共 80 个条目)
```

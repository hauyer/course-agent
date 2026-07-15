# 1.0 → 1.1 数据库迁移

1.1 使用 Alembic 维护数据库版本。迁移是增量操作：保留全部 1.0 表和数据，只增加头像、独立 Agent trace、多课程规划及知识图谱所需结构。

## 升级前

1. 关闭课程学习助手，确认没有后端仍在写数据库。
2. 检查 `.env` 中的 `DATABASE_URL` 指向预期数据库。
3. 使用 `mysqldump` 备份：

```powershell
mysqldump -h 127.0.0.1 -u course_agent -p --single-transaction course_agent > course_agent-v1-backup.sql
```

不要把备份、`.env` 或密码提交到 Git。

## 执行

```powershell
cd course-agent-backend
.\.venv\Scripts\python.exe -m alembic history
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
```

正常结果为 `0002_v1_1_features (head)`。桌面 1.1 后端启动时也会运行同一条升级链；已升级数据库不会重复修改。

## 新增结构

- `users.avatar_data`
- `chat_messages.agent_trace`
- `study_plans.plan_type/version/client_request_id/available_weekdays`
- `study_plan_courses`
- `knowledge_graph_jobs`
- `knowledge_nodes`、`knowledge_edges`
- `knowledge_node_sources`、`knowledge_edge_sources`

## 回滚

应用代码可切回 `v1.0.0-local-backup`。数据库回滚前必须保留备份；Alembic 的 1.1 downgrade 只移除 1.1 新结构，不会删除 1.0 表，但会丢失 1.1 独有的头像、综合规划关联和图谱数据，因此优先推荐恢复完整备份到新的数据库，再切换 `DATABASE_URL`。

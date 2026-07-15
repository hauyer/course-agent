# 课程学习助手前端

完整的 MySQL 配置、安全说明、开发、构建、备份迁移与 GitHub 提交指南请参阅仓库根目录的 [`README.md`](../README.md)。

## 启动

1. 先在 `course-agent-backend` 中配置 `.env` 并启动 FastAPI：

   ```powershell
   uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```

2. 开发模式：

   ```powershell
   npm install
   npm run dev
   ```

3. 桌面便携版：运行 `release/课程学习助手-便携版-1.1.0-x64.exe`。

桌面程序内置静态页面服务和 `/api` 同源代理，默认连接 `127.0.0.1:8000`，无需修改后端 CORS。

资料解析和分块成功后，后端会在后台自动建立向量索引。笔记页的“集成配置”按当前登录用户分别保存 Notion 与 Obsidian 配置；Notion Token 加密存储，留空 Token 输入框会保留原有密钥。

## 构建

```powershell
npm run build
npm run dist
```

若 Electron Builder 在含中文的工程路径中出现临时目录重命名错误，可在纯英文临时路径执行打包；前端生产构建不受影响。

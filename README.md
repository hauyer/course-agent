# 课程学习助手（Course Desk）

一个面向高校课程学习场景的本地桌面工作台。它将课程、资料、知识检索、任务、学习计划、学习记录、笔记和 AI 课程问答整合在同一套界面中，帮助学习者把分散的文件和学习安排整理成可持续推进的学习流程。

项目采用 React + Electron 构建桌面端，FastAPI 提供业务与 Agent 服务，MySQL 保存结构化数据，ChromaDB 负责课程资料的本地向量检索。

## 主要功能

- **今日总览**：汇总待办任务、进行中计划、课程资料和近 14 天学习投入。
- **课程管理**：维护课程名称、教师、学期和课程说明，并支持搜索与筛选。
- **资料库**：上传并解析 PDF、Word、PowerPoint、Markdown 和文本资料，后台完成分块与向量化。
- **知识检索**：使用 SentenceTransformer 与 ChromaDB cosine 空间，在当前用户的指定课程内检索原文片段，展示页码、真实余弦相似度和资料来源。
- **可验证资料引用**：Agent 回答下方按课程和资料展示真实检索片段、页码、片段序号与相似度，历史会话仍可恢复引用。
- **任务管理**：按状态和优先级管理学习任务，任务完成后自动计入学习时长。
- **学习计划**：保留单课程计划，并支持多课程容量预览、超载提示、确认创建和安全重新生成。
- **学习记录**：记录实际投入、学习内容与复盘想法，形成可回顾的学习轨迹。
- **笔记系统**：创建、阅读和编辑 Markdown 笔记，以排版后的阅读视图呈现，并支持 Notion、Obsidian 同步。
- **课程问答**：围绕指定课程资料进行多轮对话，保留会话上下文，并以可折叠过程展示 Agent 与工具执行状态。
- **课程知识图谱**：按后台任务从真实资料片段提取节点、关系与证据，支持版本保护、筛选和来源查看。
- **运行审计**：查看 Agent 请求的 trace ID、耗时、模型调用、工具错误和 token 使用情况。
- **数据迁移**：通过应用内备份包导出和导入个人课程数据。

## 系统架构

```mermaid
flowchart LR
    UI["React / Vite 界面"] --> Electron["Electron 桌面宿主"]
    Electron --> API["FastAPI 服务"]
    API --> MySQL["MySQL 业务数据"]
    API --> Chroma["ChromaDB 向量索引"]
    API --> Agent["课程 Agent"]
    Agent --> LLM["外部大模型 API"]
    Agent --> Chroma
    API --> Files["本地课程资料"]
    API --> Integrations["Notion / Obsidian"]
```

桌面发行版会自动拉起内置的 FastAPI 可执行程序，不需要用户单独安装 Python；MySQL 仍由用户在本机安装和管理。

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 桌面端 | Electron、electron-builder |
| 前端 | React、TypeScript、Vite、Recharts、React Markdown、KaTeX |
| 后端 | FastAPI、SQLAlchemy、Pydantic |
| Agent | LangGraph/LangChain 风格状态编排、流式事件、会话记忆 |
| 数据 | MySQL、ChromaDB、本地文件存储 |
| 文档处理 | PyMuPDF、Office/文本解析、可选 OCR |

## 项目结构

```text
course-agent/
├─ course-agent-backend/       FastAPI、Agent、数据库、资料解析和向量检索
│  ├─ app/
│  │  ├─ agent/                Agent 状态、工具与接口
│  │  ├─ routers/              REST API 路由
│  │  ├─ models/               SQLAlchemy 数据模型
│  │  ├─ schemas/              请求与响应模型
│  │  └─ services/             文档、向量、备份、审计等服务
│  ├─ requirements.txt
│  └─ .env.example
├─ course-agent-frontend/      React 页面与 Electron 桌面程序
│  ├─ src/features/            课程、资料、问答、计划、笔记等业务模块
│  ├─ src/components/          通用组件
│  ├─ src/shared/              通用异步状态与跨业务基础能力
│  ├─ electron/                桌面主进程与运行配置
│  └─ package.json
├─ .github/workflows/          持续集成检查
└─ README.md
```

本地还可能看到 `.venv`、`node_modules`、`dist`、`release-*`、`uploads`、
`chroma_db`、`vite.config.js` 等目录或文件。它们分别属于本机依赖、构建产物、
用户资料、向量索引或 TypeScript 生成文件，均已由根 `.gitignore` 排除，不属于
GitHub 源码结构。为了保留本机可运行环境，日常整理仓库时不需要删除它们。

## 1.1 余弦检索

1.1 将原有“归一化向量 + 默认 L2 collection”升级为独立的显式 cosine collection，同时完整保留旧索引用于回滚：

- 资料片段与查询使用同一个 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` 模型。
- 两端均使用 `normalize_embeddings=True`。
- 新 collection：`course_material_chunks_v1_1_cosine`。
- Chroma cosine distance 定义为 `1 - cosine_similarity`。
- 接口中的 `similarity_score = 1 - distance`，是真实余弦相似度。
- Chroma 初筛和 MySQL 二次校验都限定 `user_id + course_id`。
- 默认最低相似度为 `0.35`，低于阈值的片段不会交给 Agent。
- 普通知识检索、Agent 上下文和回答引用共用同一个检索服务。

先 dry-run，再重建和校验；脚本不会修改 `.env` 或删除旧 collection：

```powershell
cd course-agent-backend
.\.venv\Scripts\python.exe scripts\rebuild_cosine_vectors.py
.\.venv\Scripts\python.exe scripts\rebuild_cosine_vectors.py --apply --yes
.\.venv\Scripts\python.exe scripts\validate_cosine_collection.py
```

详细说明见：

- [余弦检索原理与 API](docs/v1.1-cosine-retrieval.md)
- [向量迁移与切换](docs/v1.1-vector-migration.md)
- [回滚方案](docs/v1.1-retrieval-rollback.md)
- [测试报告](docs/v1.1-retrieval-test-report.md)

## 下载与使用

Windows 用户可在仓库的 [Releases](https://github.com/hauyer/course-agent/releases) 页面下载：

- **安装版**：支持选择安装目录，并创建桌面快捷方式。
- **便携版**：无需安装，直接运行，适合放在移动硬盘或临时环境中使用。

两个版本都已经包含前端、FastAPI 后端、Python 运行时和必要依赖，但不包含 MySQL 服务、真实数据库密码或大模型 API Key。

### 1. 准备 MySQL

推荐使用 MySQL 8.0 或更高版本。不要让应用直接使用 `root` 账号，可以在 MySQL 中创建独立数据库和最小权限用户：

```sql
CREATE DATABASE course_agent
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

CREATE USER 'course_agent'@'localhost'
  IDENTIFIED BY '请替换为自己的强密码';

GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES
  ON course_agent.* TO 'course_agent'@'localhost';

FLUSH PRIVILEGES;
```

数据库默认连接地址为 `127.0.0.1:3306`。桌面程序不再显示数据库配置页，启动后直接进入登录界面。请在当前 Windows 用户的 `%APPDATA%\课程学习助手\.env` 中保存本机配置（该文件不会进入安装包）：

```env
DATABASE_URL=mysql+pymysql://course_agent:你的密码@127.0.0.1:3306/course_agent?charset=utf8mb4
SECRET_KEY=请替换为随机生成的长字符串
```

密码包含 `@`、`:`、`/` 等 URL 特殊字符时需要先进行 URL 编码。开发版继续读取 `course-agent-backend/.env`。旧版本已经通过首次配置页保存的 Windows 加密配置仍然兼容。

### 2. 创建应用账号

程序没有预设用户名和密码。第一次进入登录页时点击“没有账户？创建一个”，注册自己的本地账号即可。

### 3. 配置大模型

登录后打开“设置”，先验证当前账号密码，再填写兼容的外部大模型 API Key。密钥只保存在本机配置中，不应写入源码或提交到仓库。

## 本地开发

### 环境要求

- Windows 10/11
- Python 3.13（当前开发环境验证版本为 3.13.9）
- Node.js 24（当前开发环境验证版本为 24.15.0）
- MySQL 8.0+
- 可选：Tesseract OCR，用于识别扫描版 PDF

### 1. 启动后端

```powershell
cd course-agent-backend
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

编辑 `.env`，至少配置数据库连接和 JWT 密钥：

```env
DATABASE_URL=mysql+pymysql://course_agent:你的密码@127.0.0.1:3306/course_agent?charset=utf8mb4
SECRET_KEY=请替换为随机生成的长字符串
```

如需使用 Agent，在 `.env` 中继续配置模型名称和对应的 API Key。随后启动服务：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

后端健康检查：<http://127.0.0.1:8000/health>

启动时会自动执行 Alembic 增量迁移。手动检查迁移链：

```powershell
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic history
.\.venv\Scripts\python.exe -m alembic upgrade head
```

1.0 数据库升级只新增 1.1 字段和表，不删除课程、资料、任务、计划或聊天记录。生产数据升级前仍应先使用 `mysqldump` 备份，详见 [1.1 数据库迁移](docs/database-migration-v1.1.md)。

### 2. 启动前端

另开一个 PowerShell 窗口：

```powershell
cd course-agent-frontend
npm install
npm run dev
```

开发环境通过 Vite 代理访问 `127.0.0.1:8000`。

## 构建 Windows 桌面程序

```powershell
cd course-agent-frontend
npm install
npm run dist
```

构建流程会先使用 PyInstaller 打包 FastAPI 后端，再构建 React 前端，最后由 electron-builder 生成安装版和便携版。产物位于：

```text
course-agent-frontend/release/
├─ 课程学习助手-安装版-1.1.0-x64.exe
└─ 课程学习助手-便携版-1.1.0-x64.exe
```

发行包体积较大，应上传到 GitHub Releases，不要直接提交进 Git 仓库。

## 数据与隐私

- `.env`、API Key、数据库密码不会提交到仓库。
- `uploads/` 保存本地课程资料，`chroma_db/` 保存可重建的向量索引。
- 应用内导出包包含课程、任务、计划、笔记、学习记录和对话等个人数据，请妥善保管。
- 导出包不包含登录密码、大模型 API Key、Notion Token 和本机 Obsidian 路径。
- 更换电脑时，应先安装 MySQL、创建空数据库和应用账号，再通过“设置 → 数据备份与迁移”导入备份。
- 不建议将 MySQL 3306 端口直接暴露到公网；跨设备连接时应限制来源并启用 TLS。

## 资料解析说明

普通文本 PDF 会直接提取文本；扫描版 PDF 可通过 OCR 辅助识别。若原文件的字体映射或数学公式在解析阶段已经丢失，程序只能标记文本层质量问题，无法凭空恢复原始字符。遇到此类资料时，建议更换带有正常文本层的 PDF，或使用 OCR 版本重新上传。

## 常用检查

```powershell
# 后端语法检查
cd course-agent-backend
.\.venv\Scripts\python.exe -m compileall -q app
.\.venv\Scripts\python.exe -m pytest -q

# 前端类型检查与生产构建
cd ..\course-agent-frontend
npm run build
```

## 常见问题

- **程序无法进入登录页**：确认 MySQL 服务正在运行，数据库、账号和密码与配置一致。
- **端口 8000 被占用**：关闭之前残留的课程学习助手或 Python 后端进程后重试。
- **上传后长时间处理中**：大文件解析、OCR 和首次向量模型加载需要时间，可在资料库查看后台状态。
- **第一次检索较慢**：嵌入模型可能正在首次下载或加载，完成后会使用本地缓存。
- **对话无法回答课程内容**：确认资料已经完成解析和向量化，并在问答页面选择了正确课程。

## 仓库

- GitHub：<https://github.com/hauyer/course-agent>
- 问题反馈：<https://github.com/hauyer/course-agent/issues>

# Echo API

Echo 后端采用 FastAPI 分层设计：`controller -> service -> repository -> model/db`。业务数据和所有检索、图谱、缓存、任务操作都必须携带 `user_id`。

## 目录

```text
app/controllers/             HTTP 路由与 DTO 转换
app/services/                业务编排
app/repositories/            PostgreSQL 与 Neo4j 数据访问
app/models/                  SQLAlchemy ORM
app/schemas/                 Pydantic Request / Response
app/core/agent/              Function Calling、ReAct、MCP、联网工具
app/core/rag/                解析、父子分块、ES 索引与混合检索
app/core/memory/             三元组萃取、召回、反思与图谱 schema
app/core/storage/            本地文件与 OSS 抽象
app/tasks/                   Celery parse、image、memory、news 任务
migrations/                 Alembic 迁移
tests/                      RAG 与记忆可靠性测试
```

## 模型配置

模型和搜索 API Key 不写入系统环境变量。登录用户通过前端配置以下类型，密钥经 Fernet 加密后保存到 PostgreSQL：

| 类型 | 用途 |
|---|---|
| `chat` | 对话、Agent 编排、记忆萃取与反思 |
| `embedding` | 文档和记忆向量化 |
| `multimodal` | 图片理解与 OCR 增强 |
| `rerank` | 检索结果重排，可选 |
| `websearch` | 联网搜索，可选 |

## 本地运行

```powershell
uv sync
Copy-Item .env.example .env
uv run alembic upgrade head
uv run python run.py
```

Worker：

```powershell
uv run celery -A app.celery_app.celery_app worker -l info -Q default,parse,memory,news --pool=solo
uv run celery -A app.celery_app.celery_app beat -l info
```

验证：

```powershell
uv run ruff check .
uv run python -m compileall app
uv run pytest
```

## 存储约定

- PostgreSQL：账号、模型配置、知识库、文档、对话和任务状态。
- Elasticsearch：`echo_chunks`，用 `user_id + knowledge_base_id` 过滤。
- Neo4j：实体、关系、事件、溯源节点和 Insight，全部带 `user_id`。
- Redis：缓存、SSE 实时事件和 Celery broker/result backend。
- 原始文件：默认保存到 `storage/{user_id}/...`，PostgreSQL 只记录对象路径和元数据。

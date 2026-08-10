# Outcome

以当前 `D:\MyNewStart\Comet` 工作区为代码基线，将产品重建为 Echo（回声）：保留个人 AI 知识库、记忆助手、智能问答、联网检索和四存储基础设施，删除偏离个人知识与记忆主线的功能。

# Scope

- 复制 Comet 当前工作区源码，包括尚未提交的 Neo4j 记忆可靠性修改和新增文档。
- 将产品品牌、包名、容器名、数据库默认名、应用标题和用户可见文案中的 Comet/彗记统一改为 Echo/回声。
- 删除情绪计算与情绪展示、音乐库/播放/推荐。
- 删除 Celery Beat、定时任务、主动任务和任务调度 Agent 工具；保留通知渠道、每日回顾数据能力以及普通 Celery Worker。
- 删除记忆社区聚类、Community 节点/关系/API/页面入口；保留基础图谱记忆、主动检索和记忆反思。
- 保留深度研究、Verifier Loop 与研究报告。
- 保留角色卡与 Personas、Skills、多人群聊和真人微信风格。
- 保留收藏夹、通知中心、仪表盘统计、语音输入、Tracing 与成本核算。
- 删除对话分享和研究报告分享。
- 修复后端路由、模型导入、迁移链、Celery 队列、前端路由与导航，使保留功能可以独立运行。
- 更新根 README，仅描述 Echo 当前能力、启动方式、目录结构和本阶段结果。

# Non-goals

- 本阶段不重写知识库、记忆或 Agent 核心算法。
- 不迁移旧 HappyBull 数据和数据卷。
- 不复制 Comet 的 `.git`、虚拟环境、前端依赖、构建产物、缓存、日志和运行时存储。
- 不删除图片/OCR、知识图谱可视化、记忆纠错、记忆反思或 Reranker 支持。
- 不引入新的基础设施容器。

# Acceptance examples

- 页面、接口文档、容器和包元数据均显示 Echo/回声，不再出现作为产品名的 Comet/彗记。
- 前端导航中不存在音乐、主动任务、记忆社区和分享入口；研究、角色卡、Skills、群聊、收藏、通知、仪表盘与 Tracing 入口可用。
- 后端不再注册上述模块的 API，且应用导入、数据库迁移和前端类型检查通过。
- Docker Compose 仅包含 PostgreSQL、Elasticsearch、Neo4j、Redis、API、普通 Worker 和 Web，不包含 Beat 容器。
- 用户仍可注册登录、配置模型、管理知识库和记忆、对话并使用联网检索。

# Constraints and invariants

- 所有用户数据继续按 `user_id` 隔离，模型密钥继续加密存储。
- 对话保持 SSE 流式输出，知识库/记忆检索和联网搜索工具继续可用。
- PostgreSQL、Elasticsearch、Neo4j、Redis 四存储架构保持不变。
- 不覆盖或回滚从 Comet 复制来的未提交记忆可靠性修改。

# Decisions

- 用户明确不要旧 HappyBull 备份，允许不可恢复地删除旧工作区内容。
- 复制 Comet 当前工作区而非干净 HEAD，但保留 HappyBull 自身 `.git`，不继承 Comet 远程仓库。
- 品牌显示使用 Echo（回声）；内部技术标识统一使用 `echo` 或 `echo-*`。
- 删除周期性主动行为，但保留用户发起对话时的知识库和记忆自动检索。
- 图片/OCR、记忆纠错、记忆反思、图谱可视化和 Reranker 暂时保留。
- 深度研究、Verifier Loop、Personas、Skills、群聊、真人模式、收藏、通知、仪表盘、ASR 和 Tracing/成本核算按用户修订后的范围保留。

# Open questions

无阻塞问题。

# Verification expectations

- 后端运行 Ruff、Python 导入检查和现有核心测试。
- 前端运行 TypeScript 类型检查和生产构建。
- Docker Compose 运行配置解析检查，并确认服务/队列清单符合范围。
- 扫描产品源码和文档中的残余品牌及已删除模块引用。

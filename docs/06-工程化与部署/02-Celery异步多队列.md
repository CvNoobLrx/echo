# Celery 异步多队列

Echo 使用普通 Worker 执行耗时任务，并运行一个独立 Celery Beat。Beat 只有一项职责：每天北京时间 08:00 派发新闻晨报，不扫描任务表，也不提供通用定时任务系统。

| 队列 | 任务 |
|---|---|
| `default` | 连通性与通用后台任务 |
| `parse` | 文档解析、图片识别与索引 |
| `memory` | 记忆萃取与反思 |
| `news` | 新闻检索、AI 摘要与邮件发送 |

Worker 启动命令：

```powershell
uv run celery -A app.celery_app.celery_app worker -l info -Q default,parse,memory,news --pool=solo
uv run celery -A app.celery_app.celery_app beat -l info
```

接口只负责校验、落任务状态和投递消息，耗时操作由 Worker 执行。任务中的数据库引擎按事件循环独立创建，避免 Celery 重复创建事件循环时复用失效连接。

面试问答：

**Q：为什么不把解析和记忆萃取直接放在接口里？**

A：两类任务都包含外部模型调用和多存储写入，延迟不可控。异步化可以让接口快速返回任务状态，并通过重试和幂等写入提高可靠性。

**Q：Beat 会不会重新引入 Comet 的通用定时任务？**

A：不会。Beat 配置中只有固定的每日新闻入口；记忆反思仍由用户操作或新增记忆阈值触发，不依赖周期调度。

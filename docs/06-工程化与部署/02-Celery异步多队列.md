# Celery 异步多队列

Echo 只保留普通 Worker，不运行 Celery Beat。

| 队列 | 任务 |
|---|---|
| `default` | 连通性与通用后台任务 |
| `parse` | 文档解析、图片识别与索引 |
| `memory` | 记忆萃取与反思 |

Worker 启动命令：

```powershell
uv run celery -A app.celery_app.celery_app worker -l info -Q default,parse,memory --pool=solo
```

接口只负责校验、落任务状态和投递消息，耗时操作由 Worker 执行。任务中的数据库引擎按事件循环独立创建，避免 Celery 重复创建事件循环时复用失效连接。

面试问答：

**Q：为什么不把解析和记忆萃取直接放在接口里？**

A：两类任务都包含外部模型调用和多存储写入，延迟不可控。异步化可以让接口快速返回任务状态，并通过重试和幂等写入提高可靠性。

**Q：没有 Beat 后，记忆反思怎么触发？**

A：支持用户手动触发，也可以在记忆新增达到阈值时投递一次 `memory` 队列任务，不依赖周期调度。

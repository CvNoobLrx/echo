# SSE 流式输出

Echo 的问答输出采用 Server-Sent Events。LLM 生成是服务端单向推送，SSE 基于普通 HTTP，部署和断线处理比 WebSocket 更简单。

## 事件类型

| 事件 | 用途 |
|---|---|
| `meta` | 返回会话 id 和标题 |
| `token` | 增量文本 |
| `tool_start` | 工具开始执行 |
| `tool_result` | 工具结果摘要、统计和耗时 |
| `citation` | 知识库引用 |
| `done` | 生成和落库完成 |
| `error` | 业务或模型错误 |
| `resume` / `idle` | 断线续传或无进行中任务 |

## 断线续传

生成过程中，后端把累积文本和事件写入 Redis 临时缓冲。客户端重连后先收到已有内容，再继续订阅后续事件；没有正在生成的任务则返回 `idle`，前端重新拉取数据库中的历史消息。

Nginx 必须关闭代理缓冲：

```nginx
proxy_buffering off;
proxy_cache off;
proxy_read_timeout 3600s;
```

面试问答：

**Q：为什么不用 WebSocket？**

A：当前主链路是服务端向客户端单向输出，SSE 足够且兼容现有 HTTP 鉴权和反向代理。WebSocket 更适合高频双向实时协作。

**Q：为什么事件要分类型？**

A：文本、工具状态、引用和结束信号属于不同 UI 状态。结构化事件让前端增量渲染，不需要从自然语言中反向解析执行过程。

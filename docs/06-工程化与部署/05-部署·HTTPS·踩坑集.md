# Echo 部署与 HTTPS

基础 Compose 包含 7 个服务：PostgreSQL、Elasticsearch、Neo4j、Redis、API、Worker 和 Web。生产覆盖文件限制内存、收紧存储端口并将 Web 暴露到 80/443。

部署前需要：

- 修改 `JWT_SECRET` 和 `FERNET_KEY`。
- 为 PostgreSQL 与 Neo4j 设置独立密码。
- 将证书放到 `web/certs/echo.crt` 与 `web/certs/echo.key`，或按实际域名调整 Nginx 配置。
- 确认 Elasticsearch IK 镜像已成功构建。

常见踩坑：

**Q：为什么 Compose 显示 7 个容器，不是 4 个？**

A：4 个是存储容器；完整应用还需要 API、异步 Worker 和 Web。Echo 已移除 Beat，所以从裁剪前的 8 个服务收敛为 7 个。

**Q：文档上传后一直处理中？**

A：先检查 Worker 是否订阅 `parse` 队列，再检查 Redis broker 和模型配置。API 正常不代表后台任务进程正常。

**Q：为什么生产环境不直接暴露数据库端口？**

A：数据库只需要容器内访问。生产覆盖文件将端口绑定到 `127.0.0.1`，减少公网攻击面，同时保留 SSH 隧道排查能力。

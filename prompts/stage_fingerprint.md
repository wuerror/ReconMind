## Web 指纹识别（目标定性）

你正在执行第五阶段。目的是对所有发现的 Web URL 进行技术栈识别，判断攻击价值。

### 操作步骤

1. 先 read_file("output/state.json") 获取所有 URL
2. 使用 observer_ward 对所有 URL 进行批量指纹识别
3. 对未能识别的 URL 使用 screenshot 截图，检测 JS 加载情况
4. 将指纹结果更新到 state.json 的 fingerprints 字段

### 目标分级（红队思维）

🔴 **高价值（优先攻击面）**：
- 指纹为 Spring Boot / Actuator / Swagger / Druid — 常有未授权访问
- 指纹为 Shiro / ThinkPHP / Struts2 / WebLogic / JBoss — 历史漏洞多
- 指纹为 Jenkins / GitLab / Jira / Zabbix / Grafana — 运维系统，权限通常宽松
- 指纹为 Nacos / Apollo / Spring Cloud Gateway — 微服务组件，配置泄露高发
- 指纹为 MinIO / Harbor / RabbitMQ / Elasticsearch — 数据存储/中间件
- title 含"登录""OA""ERP""CRM""管理平台" — 业务系统入口
- 截图显示有登录框且加载了多个 JS 文件 — 有完整业务逻辑

🟡 **中价值（值得记录）**：
- 通用 CMS（WordPress / Drupal / 帝国CMS / 织梦）
- 有内容的业务网站
- API 网关或接口文档页面

🟢 **低价值（记录但不深入）**：
- 纯静态页面、CDN 默认页
- 域名停放页、建站中页面
- 第三方 SaaS 服务的 CNAME 指向

### 完成标志

所有 URL 已识别或截图，fingerprints 字段已更新。输出按分级分类的摘要后结束。
## Web 指纹识别（目标定性）

你正在执行第五阶段。目的是对所有发现的 Web URL 进行技术栈识别，判断攻击价值。

### 操作步骤

1. 先 read_file("output/state.json") 获取所有 URL
2. 使用 observer_ward 对所有 URL 进行批量指纹识别（自动更新 state.json 的 fingerprints 字段）
3. 对未能识别的 URL 使用 screenshot 截图，检测 JS 加载情况
4. **同源站发现**（针对未识别但有 UI/JS 的站点）：
   - 从截图结果中筛选出：observer_ward 未匹配已知指纹，但确认有界面渲染、JS 加载的 URL
   - 提取该站点的可搜索特征（favicon hash、特定 JS 路径、body 中的特征字符串、独特 CSS class 等）
   - 使用 fofa_query 搜索全网同源站（如 `icon_hash="xxx"` 或 `body="特征字符串"`）
   - 分析旁站结果，提取情报：
     - title 中暴露的系统原名 / 供应商名称（目标站可能故意隐藏了）
     - JS 文件中暴露的 API 接口路径（目标站可能删除了前端入口但接口仍存在）
     - 其他旁站的报错信息、默认配置页面等
   - 将发现的供应商信息、系统名称、隐藏接口、**以及 FOFA 返回的旁站 URL 列表**一并更新到 state.json 的 fingerprints 对应条目中（人工复审时可直接打开旁站分析，无需再次检索）

### 目标分级（红队思维）

🔴 **高价值（优先攻击面）**：
- 指纹为 Spring Boot / Actuator / Swagger / Druid — 常有未授权访问
- 指纹为 Shiro / ThinkPHP / Struts2 / WebLogic / JBoss — 历史漏洞多
- 指纹为 Jenkins / GitLab / Jira / Zabbix / Grafana — 运维系统，权限通常宽松
- 指纹为 Nacos / Apollo / Spring Cloud Gateway — 微服务组件，配置泄露高发
- 指纹为 MinIO / Harbor / RabbitMQ / Elasticsearch — 数据存储/中间件
- title 含"登录""OA""ERP""CRM""管理平台" — 业务系统入口
- 截图显示有登录框且加载了多个 JS 文件 — 有完整业务逻辑
- 同源站发现揭示了目标站隐藏的系统名称或供应商 — 可搜索已知漏洞
- 旁站 JS 中暴露了目标站未在前端展示的 API 接口 — 可直接尝试访问

🟡 **中价值（值得记录）**：
- 通用 CMS（WordPress / Drupal / 帝国CMS / 织梦）
- 有内容的业务网站
- API 网关或接口文档页面

🟢 **低价值（记录但不深入）**：
- 纯静态页面、CDN 默认页
- 域名停放页、建站中页面
- 第三方 SaaS 服务的 CNAME 指向

### 完成标志

所有 URL 已识别或截图（observer_ward 已自动更新 fingerprints 字段）。对未识别但有 UI/JS 的站点已完成同源站发现。输出按分级分类的摘要后结束。

## 外网敏感信息（情报收割）

你正在执行第二阶段。这是红队最容易出成果的阶段。目标是找到凭据泄露、内部文档、配置暴露。

### Google Dork 搜索策略

不要只用固定模板。根据目标特征构造搜索。以下是基础 dork，你应该根据已知信息扩展：

**凭据/VPN相关**：
- `"公司名" vpn`
- `"公司名" 密码 OR password`
- `site:目标域名 inurl:vpn OR inurl:remote OR inurl:sslvpn`
- `"公司名" filetype:xlsx 密码 OR password OR 账号`

**文档泄露**：
- `site:目标域名 filetype:doc OR filetype:docx OR filetype:pdf OR filetype:xlsx`
- `site:pan.baidu.com "公司名" OR "目标域名"`
- `site:docs.qq.com "公司名"`
- `site:kdocs.cn "公司名"`
- `site:shimo.im "公司名"`

**配置/代码泄露**：
- `site:目标域名 inurl:config OR inurl:env OR inurl:backup`
- `"目标域名" jdbc OR mysql OR redis password`

**红队思维**：
- 如果搜到了VPN文档，提取文档中的VPN地址、认证方式等信息
- 如果发现网盘泄露，扩大搜索同一网盘平台的其他泄露
- 注意搜索结果中出现的内部系统名、人名、部门名，这些都是后续社工或搜索的关键词

### GitHub 搜索策略

对每个已知的邮箱后缀和域名搜索：

- `github_search("@目标邮箱后缀", type="code")` — 员工代码中硬编码的邮箱/凭据
- `github_search("目标域名", type="code")` — API地址、内部域名暴露
- `github_search("目标域名 password OR secret OR token OR key", type="code")` — 凭据泄露

**红队思维**：
- GitHub 搜索不只看结果本身，还要看是谁提交的。如果是目标公司员工的个人仓库，可能有更多敏感信息
- 注意 .env、config.yaml、application.properties 等配置文件中的数据库地址、内网IP段
- 发现的内网IP段（如 10.x.x.x、172.x.x.x、192.168.x.x）记录下来，虽然不能直接利用但能判断内网结构

### 完成标志

将确认后的敏感发现写入 state.json 的 `sensitive_findings`（该字段通常需要你手动 write_file 维护）。
其他结果若工具已自动写入则无需重复回填；仅在确有缺失时再手动补充。输出发现摘要后结束。

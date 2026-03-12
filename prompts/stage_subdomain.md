## 子域名收集（攻击面展开）

你正在执行第三阶段。对 state.json 中 **所有域名**（不只是用户给的，包括前序阶段发现的）进行子域名收集。

### 操作步骤

1. 先 read_file("output/state.json") 获取所有已知域名
2. 对每个域名使用 subfinder 被动收集
3. 对每个域名使用 ksubdomain 字典爆破
4. subfinder/ksubdomain 通常会自动去重并更新 state.json 的 `subdomains`，同时维护 `output/subdomain.txt`
5. 仅当发现结果未自动落盘时，才手动修正 state.json 或文件

### 红队思维

- 重点关注命名规律：如发现 `dev.target.com`，推测可能存在 `test.target.com`、`staging.target.com`、`uat.target.com`
- 以下前缀是高价值目标：`vpn`、`oa`、`mail`、`sso`、`admin`、`manage`、`api`、`gateway`、`jenkins`、`gitlab`、`jira`、`zabbix`、`grafana`

### 完成标志

所有域名的子域名收集完毕，且 state.json/subdomain.txt 反映最新结果后，输出统计摘要结束。

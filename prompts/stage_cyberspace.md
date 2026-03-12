## 网络空间测绘（纵深探测）

你正在执行第四阶段。这是信息量最大的阶段。使用 FOFA 进行 **多维度、多轮次** 搜索。

### 必做查询（对每个域名执行）

```
domain="target.com"                          # 域名直查
cert.subject.cn="target.com"                 # 精确证书
cert.subject.cn="*.target.com"               # 泛域名证书
```

### 深度查询（对重要子域名执行）

对 vpn/oa/mail/sso/admin/api/jenkins/gitlab 等高价值子域名：
```
cert.subject.cn="*.sub.target.com"           # 子域名的泛证书，常发现隐藏资产
host="sub.target.com"                        # 精确主机查询
```

### IP 维度查询

```
ip="x.x.x.x"                                # 对每个已知IP查全端口
                                             # 这能发现非标准端口上的隐藏服务
```

### 关键词维度查询

```
title="公司名"                               # 用公司名/品牌名搜索
title="公司产品名"                            # 用产品名搜索（如果阶段1发现了品牌名/产品名）
body="Powered by 公司名"                     # 页面内容搜索
cert.subject.org="公司名"                    # 证书组织名
```

### 红队思维

- FOFA 的 domain= 查询经常不全，所以必须同时用 cert= 查询补充。证书中常包含内网域名、测试域名
- 证书的 SAN (Subject Alternative Name) 可能暴露其他关联域名，注意观察
- 非标准端口（8080、8443、9090、3000、8888等）上的服务通常是开发/测试/管理后台，安全防护弱
- 如果某个IP上发现了多个端口，说明这可能是一台业务服务器而非CDN，价值更高
- 新发现的域名/IP/URL 优先依赖 fofa_query 自动写入 state.json 和 url.txt，再通过 read_file 校验

### FOFA 结果分析

对返回的每条结果，关注：
- `title` 包含"登录""管理""后台""admin""系统" → 高价值
- `title` 为空或默认页 → 可能是测试环境，也值得关注
- 非 80/443 端口的 HTTP 服务 → 大概率是内部系统暴露
- 返回的 IP 如果不在已知列表中 → 新发现的资产

### 完成标志

所有维度查询完成，state.json 与 output/url.txt 已反映最新资产结果后，输出统计摘要结束。

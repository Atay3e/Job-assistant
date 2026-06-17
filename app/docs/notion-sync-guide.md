# Notion 同步设置

这个小应用会把本地岗位 tracker 同步到一个 Notion 数据库。岗位 URL 会作为去重依据：如果 Notion 里已经有同一个 URL，就更新那一行；如果没有，就创建新行。

## 1. 新建 Notion 数据库

在 Notion 里新建一个 Table database，并创建这些必需字段，字段名要完全一致：

| 字段名 | 类型 |
| --- | --- |
| Name | Title |
| Status | Status |
| URL | URL |
| position | Text |
| JD | Text |

建议再加这些字段，方便按日期筛选和复盘：

| 字段名 | 类型 | 用途 |
| --- | --- | --- |
| Company | Text | 公司 |
| Source | Select | 来源平台 |
| Score | Number | 匹配分 |
| Timeline Date | Date | 时间线主日期 |
| Batch Date | Date | 推荐日期 |
| Found Date | Date | 发现日期 |
| Recommended Date | Date | 推荐日期备份 |
| Applied Date | Date | 投递日期 |
| Decision | Select | Apply / Watch / Drop |
| Eligibility Flags | Multi-select | 身份或签证限制提示 |
| Resume Path | Text | 本地简历路径 |
| Cover Letter Path | Text | 本地 Cover Letter 路径 |
| Notes | Text | 匹配说明 |
| Last Checked | Date | 最后检查日期 |

## 2. 连接 integration

打开这张数据库表，点右上角菜单，找到 Connections，把你的 Notion integration 添加进去。只创建 token 还不够，必须把 integration 显式连接到这张数据库，否则 API 看不到它。

## 3. 填本地配置

在本应用目录下创建 `.env.local`：

```ini
NOTION_TOKEN=你的 integration token
NOTION_DATABASE_ID=你的 database id
```

保存后重启本地小应用，再进入网页的 Notion 页面点击“同步岗位”。

## 4. 按时间查看

Notion 里可以直接用 `Timeline Date` 筛选某一天，也可以筛选 `Timeline Date` 在某个月内。这个字段优先使用投递日期，其次使用推荐日期/发现日期。

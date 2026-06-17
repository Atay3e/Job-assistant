# 求职助手

一个本地优先的个人求职工作台，用来扫描岗位、分析简历定位、推荐适合岗位、管理公司关注、生成申请材料，并保留人工确认边界。

## 功能

- 多地区画像：Singapore、China Mainland、Hong Kong。
- 本地 SQLite 岗位追踪。
- 每日扫描、来源状态和失败记录。
- 今日推荐：保留 5.0 基础评分，叠加地区、城市、方向和关注公司排序。
- 职业定位：上传 PDF/DOCX/MD/TXT 简历并本地分析。
- 公司雷达：关注默认公司目录或添加自定义官网招聘链接。
- Apply / Watch / Drop 决策流。
- 辅助填表：打开浏览器并停在最终提交前。
- 本地日报和 Notion 同步入口。

## 运行

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
python .\server.py
```

然后打开：

```text
http://127.0.0.1:8787
```

也可以使用：

```powershell
.\Start-Job-Assistant.ps1 -Open
```

## 配置

复制 `.env.example` 为 `.env.local`，再按需填写：

```text
JOB_ASSISTANT_HOST=127.0.0.1
JOB_ASSISTANT_PORT=8787
JOB_ASSISTANT_RESUME=
```

## 本地数据

以下内容只保存在本机，不应提交到公开仓库：

- `data/`
- `workspace/`
- `logs/`
- `.env.local`
- 浏览器档案、SQLite 数据库、简历、生成的申请材料和日报

## 安全边界

求职助手不会自动提交真实申请，也不会自动把岗位标记为 Applied。最终提交和 Applied 确认仍由用户手动完成。

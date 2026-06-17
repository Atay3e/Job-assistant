# 求职助手

本地优先的个人求职工作台：维护求职画像、扫描岗位、关注公司、分析简历定位、推荐岗位、准备申请材料，并追踪 Apply / Watch / Drop 状态。

## Highlights

- Multi-region profile: Singapore, China Mainland, Hong Kong
- Resume upload and local-first career-fit analysis
- Company radar with built-in catalogs and custom career URLs
- Daily scanner with visible source status
- 5.0 base scoring plus preference, region, city, and watched-company ranking
- Browser-assisted application flow that stops before final submission
- Local SQLite source of truth

## Run Locally

```powershell
cd app
python -m pip install -r requirements.txt
python -m playwright install chromium
python .\server.py
```

Open:

```text
http://127.0.0.1:8787
```

## Privacy

Runtime data is intentionally ignored by Git:

- `app/data/`
- `app/workspace/`
- `app/logs/`
- `.env.local`

Do not commit personal resumes, generated application materials, browser profiles, SQLite databases, or API keys.

# Deploy 求职助手

`http://127.0.0.1:8787` is local-only. It works only while the app is running on your own computer.

## What Can Host This App

GitHub can host the repository and run CI, but GitHub Pages cannot run this app because 求职助手 has a Python backend, SQLite data, file uploads, scanners, and browser-assisted application flows.

Vercel is not the best direct target for the current version. It is excellent for frontends and serverless APIs, but this app currently expects a long-running Python process, local SQLite files, background scans, and Playwright support. A Vercel version would need a product refactor: external database, object storage, auth, and serverless-safe APIs.

Render or Railway are better first deployment targets because they can run the existing Docker app with much less rewrite.

## Render Free Deploy

Open:

```text
https://render.com/deploy?repo=https://github.com/Atay3e/Job-assistant
```

Use the default blueprint settings:

- Service name: `job-assistant`
- Environment: Docker
- Plan: free
- Health check: `/api/health`

The free blueprint uses temporary storage:

```text
JOB_ASSISTANT_HOST=0.0.0.0
JOB_ASSISTANT_DATA_DIR=/tmp/job-assistant/app-data
JOB_ASSISTANT_WORKSPACE_DIR=/tmp/job-assistant/workspace
```

This makes the free deployment pass Render's validation. The tradeoff is that uploaded resumes, SQLite data, and generated workspace files are not guaranteed to survive restarts or redeploys.

## Stable Data Options

For a real public product, use one of these:

1. Render paid web service with a persistent disk, then set:

```text
JOB_ASSISTANT_DATA_DIR=/data/app-data
JOB_ASSISTANT_WORKSPACE_DIR=/data/workspace
```

2. Refactor to external storage:

- Postgres or Supabase for jobs, profiles, applications, and scan runs
- S3 or Cloudflare R2 for resumes and generated documents
- Login/account separation before opening it to many users

## Privacy Note

Do not upload local runtime folders to public hosting:

- `app/data/`
- `app/workspace/`
- `app/logs/`
- `.env`

The current free deploy path is good for demos and early testing. For real public users, add account separation and persistent external storage first.

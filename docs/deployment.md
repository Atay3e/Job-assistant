# Deploy 求职助手

`http://127.0.0.1:8787` is local-only. It works only while the app is running on your own computer.

## What Can Host This App

GitHub can host the repository and run CI, but GitHub Pages cannot run this app because 求职助手 has a Python backend, SQLite data, file uploads, scanners, and browser-assisted application flows.

Vercel is not the best direct target for the current version. It is excellent for frontends and serverless APIs, but this app currently expects a long-running Python process, local SQLite files, background scans, and Playwright support. A Vercel version would need a product refactor: external database, object storage, auth, and serverless-safe APIs.

Render or Railway are better first deployment targets because they can run the existing Docker app with much less rewrite.

## Render Deploy

Open:

```text
https://render.com/deploy?repo=https://github.com/Atay3e/Job-assistant
```

Use the default blueprint settings:

- Service name: `job-assistant`
- Environment: Docker
- Plan: starter
- Health check: `/api/health`
- Persistent disk: `/data`

The blueprint stores runtime files under the persistent disk:

```text
JOB_ASSISTANT_HOST=0.0.0.0
JOB_ASSISTANT_DATA_DIR=/data/app-data
JOB_ASSISTANT_WORKSPACE_DIR=/data/workspace
JOB_ASSISTANT_REQUIRE_AUTH=1
```

Render services without a persistent disk use temporary storage, so uploaded resumes, SQLite data, and generated workspace files are not guaranteed to survive restarts or redeploys.

## Supabase Auth

Before sharing the app with friends, create a Supabase project and add these Render environment variables:

```text
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_JWT_SECRET=
SUPABASE_SERVICE_ROLE_KEY=
APP_SECRET_KEY=
```

With auth enabled, every private API request requires a Supabase login token. Each user gets a separate data directory under `/data/app-data/users/<user_id>/`, so preferences, resumes, queues, applied jobs, watched companies, scan records, and Notion settings do not mix.

## Owner Data Migration

After creating your own Supabase account, copy your existing local data into your account-scoped storage:

```text
cd app
python scripts/migrate_local_owner.py --user-id YOUR_SUPABASE_USER_ID
```

Friends should create their own accounts and start from empty data.

## Future Vercel Split

Vercel can be useful later for a frontend-only deployment, but this current Python app still runs a long-lived backend with scanners, uploads, local browser assist, and Playwright. Keep the backend on Render or Railway unless the API is refactored for serverless storage and background jobs.

## Privacy Note

Do not upload local runtime folders to public hosting:

- `app/data/`
- `app/workspace/`
- `app/logs/`
- `.env`

The current deploy path is meant for authenticated friends, not anonymous public traffic.

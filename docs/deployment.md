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
- Plan: free
- Health check: `/api/health`

The blueprint uses temporary local files for the running container and Supabase Storage for durable user state:

```text
JOB_ASSISTANT_HOST=0.0.0.0
JOB_ASSISTANT_DATA_DIR=/tmp/job-assistant/app-data
JOB_ASSISTANT_WORKSPACE_DIR=/tmp/job-assistant/workspace
JOB_ASSISTANT_REQUIRE_AUTH=1
SUPABASE_STORAGE_BUCKET=job-assistant-users
```

Render Free services use temporary storage, so the app automatically stores each authenticated user's state bundle in Supabase Storage. On restart or redeploy, the first logged-in request restores that user's profile, resumes, queue, applied records, watched companies, scan records, generated materials, and Notion settings.

## Supabase Auth

Before sharing the app with friends, create a Supabase project and add these Render environment variables:

```text
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_JWT_SECRET=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_STORAGE_BUCKET=job-assistant-users
APP_SECRET_KEY=
```

With auth enabled, every private API request requires a Supabase login token. Each user gets a separate temporary data directory under `JOB_ASSISTANT_DATA_DIR/users/<user_id>/`, and that directory is synced to Supabase Storage after writes. Preferences, resumes, queues, applied jobs, watched companies, scan records, generated files, and Notion settings do not mix.

The backend uses the service role key only on the server to create and update private state archives. Never expose `SUPABASE_SERVICE_ROLE_KEY` in frontend code.

To avoid pasting secrets into chat, save those values locally in `app/.env.supabase.local` and run:

```text
cd app
python scripts/configure_render_supabase.py
```

The file is ignored by Git.

## Owner Data Migration

After creating your own Supabase account, copy your existing local data into your account-scoped local folder, then sign in once and make any save action so it syncs to Supabase Storage:

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

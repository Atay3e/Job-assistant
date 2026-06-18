# Deploy 求职助手

`http://127.0.0.1:8787` is a local-only address. It works only while the app is running on your own computer.

For a stable URL that other people can open, deploy the app to a web service. The repository includes a Dockerfile and a Render blueprint.

## One-Click Render Deploy

Open:

```text
https://render.com/deploy?repo=https://github.com/Atay3e/Job-assistant
```

Use the default blueprint settings:

- Service name: `job-assistant`
- Environment: Docker
- Health check: `/api/health`
- Persistent disk: `/data`

Render will generate a public URL similar to:

```text
https://job-assistant.onrender.com
```

## Environment Variables

The blueprint sets the required public-hosting values:

```text
JOB_ASSISTANT_HOST=0.0.0.0
JOB_ASSISTANT_DATA_DIR=/data/app-data
JOB_ASSISTANT_WORKSPACE_DIR=/data/workspace
```

Most cloud platforms provide `PORT` automatically. The app now uses that value when present.

## Privacy Note

Do not upload local runtime folders to public hosting:

- `app/data/`
- `app/workspace/`
- `app/logs/`
- `.env`

For a public multi-user product, the next step is adding account separation. This first deployment path is suitable for demos, private beta, and controlled sharing.

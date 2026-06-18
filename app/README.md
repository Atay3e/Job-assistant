# 求职助手 App

这是求职助手的本地应用服务，包含网页界面、SQLite 数据库、扫描器、简历定位和投递辅助 API。

## 本地运行

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
.\Start-Job-Assistant.ps1 -Open
```

打开：

```text
http://127.0.0.1:8787
```

如果页面打不开，优先重新运行：

```powershell
.\Start-Job-Assistant.ps1 -Open
```

启动脚本会检查 `/api/health`，并在旧服务卡住时重启自己的后端进程。

## 配置

复制 `.env.example` 为 `.env.local`，再按需填写：

```text
JOB_ASSISTANT_HOST=127.0.0.1
JOB_ASSISTANT_PORT=8787
JOB_ASSISTANT_DATA_DIR=
JOB_ASSISTANT_WORKSPACE_DIR=
JOB_ASSISTANT_RESUME=
```

云平台通常会自动提供 `PORT`，服务会优先使用它。

## 公开部署

不要把 `127.0.0.1` 发给别人。它只代表访问者自己的电脑。

公开部署请看根目录的 `docs/deployment.md`。推荐使用 Render 的 Blueprint 部署：

```text
https://render.com/deploy?repo=https://github.com/Atay3e/Job-assistant
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

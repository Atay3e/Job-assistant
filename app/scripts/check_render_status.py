from __future__ import annotations

import json
import subprocess
from pathlib import Path


SERVICE_ID = "srv-d8tujlho3t8c73c3h60g"
PUBLIC_URL = "https://job-assistant-nwfs.onrender.com"


def render_api_key() -> str:
    config = Path.home() / ".render" / "cli.yaml"
    if not config.exists():
        raise SystemExit("Render CLI is not logged in. Run: render login")
    parent = ""
    for raw in config.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        if indent == 0:
            parent = raw.split(":", 1)[0].strip()
        elif parent == "api" and raw.strip().startswith("key:"):
            value = raw.split(":", 1)[1].strip().strip('"')
            if value:
                return value
    raise SystemExit("Could not read Render API key from CLI config. Run: render login")


def curl_json(url: str, key: str | None = None, timeout: int = 30) -> dict | list:
    command = ["curl", "-fsS", url, "-H", "Accept: application/json"]
    if key:
        command.extend(["-H", f"Authorization: Bearer {key}"])
    try:
        result = subprocess.run(command, text=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise SystemExit(
            f"Timed out after {timeout}s waiting for {url}. The Render free service may be in a cold start or unavailable."
        ) from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        if key and "401" in detail:
            raise SystemExit("Render CLI login has expired. Run `render login`, then retry this check.")
        raise SystemExit(detail)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Expected JSON from {url}, but received an invalid response.") from exc


def safe_public_json(url: str, timeout: int) -> dict | list:
    try:
        return curl_json(url, timeout=timeout)
    except SystemExit as exc:
        return {"ok": False, "error": str(exc)}


def main() -> None:
    render_key = render_api_key()
    service = curl_json(f"https://api.render.com/v1/services/{SERVICE_ID}", render_key)
    deploys = curl_json(f"https://api.render.com/v1/services/{SERVICE_ID}/deploys?limit=1", render_key)
    env_vars = curl_json(f"https://api.render.com/v1/services/{SERVICE_ID}/env-vars", render_key)
    health = safe_public_json(f"{PUBLIC_URL}/api/health", timeout=120)
    auth = safe_public_json(f"{PUBLIC_URL}/api/auth/config", timeout=30)
    wanted = {
        "JOB_ASSISTANT_REQUIRE_AUTH",
        "SUPABASE_URL",
        "SUPABASE_ANON_KEY",
        "SUPABASE_JWT_SECRET",
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_STORAGE_BUCKET",
    }
    configured = {}
    for item in env_vars:
        env = item.get("envVar") or item
        name = env.get("key")
        value = env.get("value") or ""
        if name in wanted:
            configured[name] = "set" if value else "empty"
    latest = (deploys[0].get("deploy") or deploys[0]) if deploys else {}
    details = (service.get("service") or service).get("serviceDetails") or {}
    print(json.dumps({
        "url": PUBLIC_URL,
        "plan": details.get("plan"),
        "health": health,
        "auth": auth,
        "env": configured,
        "latest_deploy": {
            "status": latest.get("status"),
            "commit": (latest.get("commit") or {}).get("id", "")[:7],
            "message": (latest.get("commit") or {}).get("message"),
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

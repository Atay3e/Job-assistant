from __future__ import annotations

import json
import re
import secrets
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
APP_DIR = ROOT_DIR / "app"
DEFAULT_ENV_FILE = APP_DIR / ".env.supabase.local"
SERVICE_ID = "srv-d8tujlho3t8c73c3h60g"


REQUIRED = [
    "SUPABASE_URL",
    "SUPABASE_ANON_KEY",
    "SUPABASE_JWT_SECRET",
    "SUPABASE_SERVICE_ROLE_KEY",
]


def looks_like_jwt(value: str) -> bool:
    return bool(re.match(r"^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$", value or ""))


def validate_values(values: dict[str, str]) -> None:
    url = values["SUPABASE_URL"].rstrip("/")
    if not re.match(r"^https://[A-Za-z0-9-]+\.supabase\.co$", url):
        raise SystemExit("SUPABASE_URL should look like https://xxxx.supabase.co")
    for key in ["SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY"]:
        if not looks_like_jwt(values[key]):
            raise SystemExit(f"{key} does not look like a Supabase JWT key.")
    if len(values["SUPABASE_JWT_SECRET"]) < 20:
        raise SystemExit("SUPABASE_JWT_SECRET looks too short.")
    request = urllib.request.Request(
        f"{url}/auth/v1/settings",
        headers={
            "apikey": values["SUPABASE_ANON_KEY"],
            "Authorization": f"Bearer {values['SUPABASE_ANON_KEY']}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            if response.status >= 400:
                raise SystemExit(f"Supabase settings check failed with HTTP {response.status}.")
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"Supabase anon key check failed: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Cannot reach Supabase project: {exc}") from exc


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        raise SystemExit(f"Missing {path}. Create it from app/.env.example and fill Supabase values.")
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    missing = [key for key in REQUIRED if not values.get(key)]
    if missing:
        raise SystemExit(f"Missing values in {path}: {', '.join(missing)}")
    validate_values(values)
    values.setdefault("SUPABASE_STORAGE_BUCKET", "job-assistant-users")
    values.setdefault("JOB_ASSISTANT_REQUIRE_AUTH", "1")
    values.setdefault("JOB_ASSISTANT_DATA_DIR", "/tmp/job-assistant/app-data")
    values.setdefault("JOB_ASSISTANT_WORKSPACE_DIR", "/tmp/job-assistant/workspace")
    values.setdefault("JOB_ASSISTANT_HOST", "0.0.0.0")
    values.setdefault("APP_SECRET_KEY", secrets.token_urlsafe(32))
    return values


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


def update_render_env(key: str, value: str, render_key: str) -> None:
    result = subprocess.run(
        [
            "curl",
            "-fsS",
            "-X",
            "PUT",
            f"https://api.render.com/v1/services/{SERVICE_ID}/env-vars/{key}",
            "-H",
            "Accept: application/json",
            "-H",
            "Content-Type: application/json",
            "-H",
            f"Authorization: Bearer {render_key}",
            "-d",
            json.dumps({"value": value}),
        ],
        text=True,
        capture_output=True,
        timeout=45,
    )
    if result.returncode != 0:
        raise SystemExit(f"Failed to update {key}: {result.stderr.strip()}")
    print(f"{key}=updated")


def main() -> None:
    env_file = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else DEFAULT_ENV_FILE
    values = load_env(env_file)
    key = render_api_key()
    for name, value in values.items():
        if name.startswith("SUPABASE_") or name.startswith("JOB_ASSISTANT_") or name == "APP_SECRET_KEY":
            update_render_env(name, value, key)
    print("Render Supabase environment is ready. Trigger a deploy with: render deploys create srv-d8tujlho3t8c73c3h60g --wait --confirm")


if __name__ == "__main__":
    main()

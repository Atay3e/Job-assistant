from __future__ import annotations

import getpass
import subprocess
import sys
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
SERVICE_ID = "srv-d8tujlho3t8c73c3h60g"


def run(command: list[str], *, timeout: int = 120) -> None:
    result = subprocess.run(command, text=True, timeout=timeout)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def ensure_supabase_login() -> None:
    probe = subprocess.run(
        ["supabase", "projects", "list", "--output-format", "json"],
        text=True,
        capture_output=True,
        timeout=60,
    )
    if probe.returncode == 0:
        print("Supabase CLI already logged in.")
        return
    subprocess.run(["open", "https://supabase.com/dashboard/account/tokens"], check=False)
    print("Paste a Supabase Access Token from the page that just opened.")
    token = getpass.getpass("Supabase access token: ").strip()
    if not token:
        raise SystemExit("No token entered.")
    run(["supabase", "login", "--token", token, "--output-format", "text"], timeout=60)


def main() -> None:
    ensure_supabase_login()
    run([sys.executable, str(APP_DIR / "scripts" / "autofill_supabase_from_cli.py")], timeout=120)
    run(["render", "deploys", "create", SERVICE_ID, "--wait", "--confirm"], timeout=600)
    run([sys.executable, str(APP_DIR / "scripts" / "check_render_status.py")], timeout=60)
    print("Free cloud save setup finished.")


if __name__ == "__main__":
    main()

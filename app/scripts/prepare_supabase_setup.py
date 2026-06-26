from __future__ import annotations

import subprocess
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = APP_DIR / ".env.supabase.local"


TEMPLATE = """# Fill these from your Supabase project.
# Supabase Dashboard:
# - Project URL: Project Settings > API
# - Public browser key: Project Settings > API Keys > publishable key
#   Legacy projects can use the anon key instead.
# - Server key: Project Settings > API Keys > secret key
#   Legacy projects can use the service_role key instead.
# Optional:
# - JWT secret: Project Settings > API > JWT Settings

SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_JWT_SECRET=
SUPABASE_STORAGE_BUCKET=job-assistant-users
"""


def main() -> None:
    if not ENV_FILE.exists():
        ENV_FILE.write_text(TEMPLATE, encoding="utf-8")
        print(f"Created {ENV_FILE}")
    else:
        print(f"{ENV_FILE} already exists")

    subprocess.run(["open", "https://supabase.com/dashboard/projects"], check=False)
    subprocess.run(["open", "-R", str(ENV_FILE)], check=False)
    print("Open the Supabase project, then paste the four values into app/.env.supabase.local.")


if __name__ == "__main__":
    main()

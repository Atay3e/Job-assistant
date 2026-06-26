from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

import server  # noqa: E402


def copy_path(source: Path, target: Path, overwrite: bool) -> None:
    if not source.exists():
        return
    if target.exists():
        if not overwrite:
            print(f"skip existing: {target}")
            return
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, target)
    else:
        shutil.copy2(source, target)
    print(f"copied: {source} -> {target}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Move current local Job Assistant data into one scoped user account.")
    parser.add_argument("--user-id", required=True, help="Supabase Auth user id for the owner account.")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing scoped user files.")
    args = parser.parse_args()

    user_key = server.safe_user_id(args.user_id)
    user_data_dir = server.DATA_DIR / "users" / user_key
    user_workspace_dir = server.WORKSPACE_DIR / "users" / user_key

    copy_path(server.DB_PATH, user_data_dir / "career_copilot.sqlite", args.overwrite)
    copy_path(server.PROFILE_PATH, user_data_dir / "profile.json", args.overwrite)
    copy_path(server.USER_CONTEXT_PATH, user_data_dir / "user_context.json", args.overwrite)
    copy_path(server.RESUME_UPLOAD_DIR, user_data_dir / "resumes", args.overwrite)
    copy_path(server.APPLY_ASSIST_DIR, user_data_dir / "apply-assist", args.overwrite)
    copy_path(server.BROWSER_PROFILE_DIR, user_data_dir / "browser-profile", args.overwrite)
    copy_path(server.WORKSPACE_DIR / "applications", user_workspace_dir / "applications", args.overwrite)
    copy_path(server.WORKSPACE_DIR / "reports", user_workspace_dir / "reports", args.overwrite)
    copy_path(server.WORKSPACE_DIR / "drafts", user_workspace_dir / "drafts", args.overwrite)

    print(f"owner data ready for user: {args.user_id}")


if __name__ == "__main__":
    main()

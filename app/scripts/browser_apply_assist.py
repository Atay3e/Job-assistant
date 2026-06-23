from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


def read_payload(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_result(path: Path, result: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def text_value(value) -> str:
    return str(value or "").strip()


def try_fill(locator, value: str, label: str, result: dict) -> bool:
    value = text_value(value)
    if not value:
        return False
    try:
        if locator.count() < 1:
            return False
        target = locator.first
        if not target.is_visible(timeout=700) or not target.is_enabled(timeout=700):
            return False
        current = target.input_value(timeout=700)
        if current:
            return False
        target.fill(value, timeout=1200)
        result["filled_fields"].append(label)
        return True
    except Exception:
        return False


def fill_common_fields(page, profile: dict, result: dict) -> None:
    page.set_default_timeout(1500)
    fields = [
        ("first name", profile.get("first_name"), [r"first\s*name", r"given\s*name"]),
        ("last name", profile.get("last_name"), [r"last\s*name", r"family\s*name", r"surname"]),
        ("full name", profile.get("full_name"), [r"full\s*name", r"name"]),
        ("email", profile.get("email"), [r"email"]),
        ("phone", profile.get("phone"), [r"phone", r"mobile", r"contact"]),
        ("location", profile.get("location"), [r"location", r"city"]),
        ("school", profile.get("school"), [r"school", r"university", r"institution"]),
        ("degree", profile.get("degree"), [r"degree", r"course", r"program", r"programme"]),
        ("linkedin", profile.get("linkedin"), [r"linkedin"]),
        ("portfolio", profile.get("portfolio"), [r"portfolio", r"website"]),
    ]
    for label, value, patterns in fields:
        for pattern in patterns:
            if try_fill(page.get_by_label(re.compile(pattern, re.I)), value, label, result):
                break
            token = re.sub(r"[^a-z]+", "", pattern.lower())
            if not token:
                continue
            selector = (
                f"input[name*='{token}' i], "
                f"input[id*='{token}' i], "
                f"textarea[name*='{token}' i]"
            )
            if try_fill(page.locator(selector), value, label, result):
                break


def click_apply_entry(page, result: dict) -> None:
    buttons = [
        page.get_by_role("button", name=re.compile(r"^(easy\s+)?apply(\s+now)?$", re.I)),
        page.get_by_role("link", name=re.compile(r"^(easy\s+)?apply(\s+now)?$", re.I)),
        page.get_by_role("button", name=re.compile(r"apply", re.I)),
        page.get_by_role("link", name=re.compile(r"apply", re.I)),
    ]
    for locator in buttons:
        try:
            if locator.count() < 1:
                continue
            locator.first.click(timeout=4000)
            result["actions"].append("clicked_apply_entry")
            try:
                page.wait_for_load_state("domcontentloaded", timeout=5000)
            except PlaywrightTimeoutError:
                pass
            return
        except Exception as exc:
            result["warnings"].append(f"Could not click apply entry: {exc}")


def upload_files(page, payload: dict, result: dict) -> None:
    job = payload["job"]
    resume_path = Path(job.get("resume_path") or payload["profile"].get("resume_path") or "")
    cover_path = Path(job.get("cover_letter_path") or payload["profile"].get("cover_letter_path") or "")
    try:
        file_inputs = page.locator("input[type='file']")
        count = file_inputs.count()
    except Exception:
        return
    for index in range(count):
        locator = file_inputs.nth(index)
        try:
            hint = locator.evaluate(
                """el => [
                    el.name, el.id, el.accept, el.getAttribute('aria-label'),
                    el.closest('label')?.innerText,
                    el.parentElement?.innerText
                ].filter(Boolean).join(' ').toLowerCase()"""
            )
            target = cover_path if "cover" in hint and cover_path.exists() else resume_path
            if not target.exists():
                result["warnings"].append(f"Missing upload file for input {index + 1}: {target}")
                continue
            locator.set_input_files(str(target), timeout=2500)
            result["uploaded_files"].append(str(target))
        except Exception as exc:
            result["warnings"].append(f"Could not upload file input {index + 1}: {exc}")


def collect_open_questions(page, result: dict) -> None:
    selectors = "textarea, input[type='text'], input:not([type])"
    try:
        fields = page.locator(selectors)
        count = min(fields.count(), 60)
    except Exception:
        return
    known = re.compile(r"name|email|phone|mobile|linkedin|portfolio|school|university|degree|location|city", re.I)
    for index in range(count):
        field = fields.nth(index)
        try:
            if not field.is_visible(timeout=500):
                continue
            value = field.input_value(timeout=500)
            label = field.evaluate(
                """el => [
                    el.getAttribute('aria-label'),
                    el.placeholder,
                    el.name,
                    el.id,
                    el.closest('label')?.innerText,
                    el.parentElement?.innerText
                ].filter(Boolean).join(' ').trim()"""
            )
            if value or known.search(label or ""):
                continue
            cleaned = re.sub(r"\s+", " ", label or "").strip()
            if cleaned and cleaned not in result["open_questions"]:
                result["open_questions"].append(cleaned[:280])
        except Exception:
            continue


def keep_browser_open(context, result_path: Path, result: dict) -> None:
    result["review_required"] = True
    result["status"] = "waiting_for_user_review"
    write_result(result_path, result)
    while True:
        try:
            if not context.pages:
                break
            time.sleep(2)
        except Exception:
            break


def local_chromium_executable() -> str | None:
    candidates = [
        os.environ.get("CHROME_PATH", ""),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: browser_apply_assist.py payload.json")
        return 2
    payload_path = Path(sys.argv[1])
    payload = read_payload(payload_path)
    job = payload["job"]
    profile = payload["profile"]
    result_path = Path(payload["result_path"])
    result = {
        "status": "started",
        "job_id": job.get("id"),
        "url": job.get("url"),
        "filled_fields": [],
        "uploaded_files": [],
        "open_questions": [],
        "actions": [],
        "warnings": [],
        "review_required": True,
        "submitted": False,
    }
    try:
        with sync_playwright() as p:
            launch_options = {
                "headless": bool(payload.get("headless", False)),
                "viewport": {"width": 1440, "height": 950},
            }
            browser_path = local_chromium_executable()
            if browser_path:
                launch_options["executable_path"] = browser_path
            context = p.chromium.launch_persistent_context(
                payload["browser_profile_dir"],
                **launch_options,
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(job["url"], wait_until="domcontentloaded", timeout=45000)
            click_apply_entry(page, result)
            fill_common_fields(page, profile, result)
            upload_files(page, payload, result)
            collect_open_questions(page, result)
            if payload.get("keep_open", True):
                keep_browser_open(context, result_path, result)
            else:
                result["status"] = "ready_for_review"
                write_result(result_path, result)
                context.close()
    except Exception as exc:
        result["status"] = "failed"
        result["warnings"].append(str(exc))
        write_result(result_path, result)
        print(str(exc))
        return 1
    result["status"] = "browser_closed"
    write_result(result_path, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

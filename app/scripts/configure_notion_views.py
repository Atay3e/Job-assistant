from __future__ import annotations

import datetime as dt
import json
import os
import urllib.error
import urllib.request
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
NOTION_VERSION = "2026-03-11"


def load_env() -> None:
    env_path = APP_DIR / ".env.local"
    for line in env_path.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ[key] = value


def notion_request(method: str, path: str, payload: dict | None = None, query: dict | None = None) -> dict:
    url = f"https://api.notion.com/v1{path}"
    if query:
        from urllib.parse import urlencode

        url += "?" + urlencode(query)
    body = None if payload is None else json.dumps(payload, ensure_ascii=True).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {os.environ['NOTION_TOKEN']}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"{method} {path} failed {exc.code}: {detail}") from exc


def table_configuration() -> dict:
    return {
        "type": "table",
        "properties": [
            {"property_id": "Company", "visible": True, "width": 220, "wrap": True},
            {"property_id": "Stage", "visible": True, "width": 140},
            {"property_id": "Position", "visible": True, "width": 270, "wrap": True},
            {"property_id": "Score", "visible": True, "width": 90},
            {"property_id": "Timeline Date", "visible": True, "width": 145, "date_format": "year_month_day", "time_format": "hidden"},
            {"property_id": "Found Date", "visible": True, "width": 135, "date_format": "year_month_day", "time_format": "hidden"},
            {"property_id": "Applied Date", "visible": True, "width": 135, "date_format": "year_month_day", "time_format": "hidden"},
            {"property_id": "Source", "visible": True, "width": 125},
            {"property_id": "Link", "visible": True, "width": 260},
            {"property_id": "JD", "visible": False},
            {"property_id": "Notes", "visible": False},
        ],
        "wrap_cells": False,
        "frozen_column_index": 1,
        "show_vertical_lines": True,
    }


def month_range(reference_date: dt.date) -> tuple[str, str, str]:
    start = reference_date.replace(day=1)
    if start.month == 12:
        next_month = dt.date(start.year + 1, 1, 1)
    else:
        next_month = dt.date(start.year, start.month + 1, 1)
    return start.isoformat(), next_month.isoformat(), start.strftime("%Y-%m")


def make_views(timeline_property_id: str) -> list[dict]:
    today = dt.date.today()
    month_start, next_month_start, month_label = month_range(today)
    return [
        {
            "name": "投递 · 全部",
            "type": "table",
            "filter": {"property": "Timeline Date", "date": {"is_not_empty": True}},
            "sorts": [
                {"property": "Timeline Date", "direction": "descending"},
                {"property": "Score", "direction": "descending"},
            ],
            "quick_filters": {
                "Timeline Date": {"date": {"is_not_empty": True}},
                "Stage": {"status": {"does_not_equal": "No Answer"}},
            },
            "configuration": table_configuration(),
        },
        {
            "name": f"投递 · 今天 {today.isoformat()}",
            "type": "table",
            "filter": {"property": "Timeline Date", "date": {"equals": today.isoformat()}},
            "sorts": [{"property": "Score", "direction": "descending"}],
            "quick_filters": {"Stage": {"status": {"does_not_equal": "No Answer"}}},
            "configuration": table_configuration(),
        },
        {
            "name": f"投递 · {month_label}",
            "type": "table",
            "filter": {
                "and": [
                    {"property": "Timeline Date", "date": {"on_or_after": month_start}},
                    {"property": "Timeline Date", "date": {"before": next_month_start}},
                ]
            },
            "sorts": [
                {"property": "Timeline Date", "direction": "descending"},
                {"property": "Score", "direction": "descending"},
            ],
            "quick_filters": {
                "Timeline Date": {"date": {"on_or_after": month_start}},
                "Stage": {"status": {"does_not_equal": "No Answer"}},
            },
            "configuration": table_configuration(),
        },
        {
            "name": "投递 · 已投",
            "type": "table",
            "filter": {"property": "Applied Date", "date": {"is_not_empty": True}},
            "sorts": [{"property": "Applied Date", "direction": "descending"}],
            "quick_filters": {"Applied Date": {"date": {"is_not_empty": True}}},
            "configuration": table_configuration(),
        },
        {
            "name": "投递时间轴 · 月视图",
            "type": "timeline",
            "filter": {"property": "Timeline Date", "date": {"is_not_empty": True}},
            "sorts": [{"property": "Score", "direction": "descending"}],
            "quick_filters": {"Timeline Date": {"date": {"is_not_empty": True}}},
            "configuration": {
                "type": "timeline",
                "date_property_id": timeline_property_id,
                "properties": [
                    {"property_id": "Stage", "visible": True},
                    {"property_id": "Position", "visible": True},
                    {"property_id": "Score", "visible": True},
                    {"property_id": "Link", "visible": True},
                ],
            },
        },
    ]


def main() -> None:
    load_env()
    database_id = os.environ["NOTION_DATABASE_ID"]
    database = notion_request("GET", f"/databases/{database_id}")
    data_source_id = database["data_sources"][0]["id"]
    data_source = notion_request("GET", f"/data_sources/{data_source_id}")
    timeline_property_id = data_source["properties"]["Timeline Date"]["id"]

    listed = notion_request("GET", "/views", query={"database_id": database_id}).get("results", [])
    existing = {}
    deleted = []
    obsolete_prefixes = ("时间线 ·", "时间轴 ·")
    for item in listed:
        view = notion_request("GET", f"/views/{item['id']}")
        name = view.get("name", "")
        if "?" in name and name.strip("? ·") == "" or name.startswith(obsolete_prefixes):
            notion_request("DELETE", f"/views/{item['id']}")
            deleted.append({"name": name, "id": item["id"]})
            continue
        existing[name] = item["id"]

    results = []
    for view_spec in make_views(timeline_property_id):
        payload = {
            "data_source_id": data_source_id,
            "name": view_spec["name"],
            "type": view_spec["type"],
            "filter": view_spec["filter"],
            "sorts": view_spec["sorts"],
            "quick_filters": view_spec.get("quick_filters"),
            "configuration": view_spec["configuration"],
        }
        if view_spec["name"] in existing:
            view_id = existing[view_spec["name"]]
            update_payload = {key: value for key, value in payload.items() if key not in {"data_source_id", "type"}}
            view = notion_request("PATCH", f"/views/{view_id}", update_payload)
            action = "updated"
        else:
            payload["database_id"] = database_id
            view = notion_request("POST", "/views", payload)
            action = "created"
        results.append({"name": view["name"], "action": action, "url": view.get("url")})

    print(json.dumps({"deleted": deleted, "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

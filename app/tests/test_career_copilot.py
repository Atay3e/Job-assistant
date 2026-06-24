from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import time
import unittest
import webbrowser
from pathlib import Path
from unittest import mock

import server


FIXTURES = Path(__file__).parent / "fixtures"


class TempAppMixin:
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.old_paths = {
            "DATA_DIR": server.DATA_DIR,
            "WORKSPACE_DIR": server.WORKSPACE_DIR,
            "DB_PATH": server.DB_PATH,
            "PROFILE_PATH": server.PROFILE_PATH,
            "USER_CONTEXT_PATH": server.USER_CONTEXT_PATH,
            "APPLY_ASSIST_DIR": server.APPLY_ASSIST_DIR,
            "BROWSER_PROFILE_DIR": server.BROWSER_PROFILE_DIR,
            "RESUME_UPLOAD_DIR": server.RESUME_UPLOAD_DIR,
        }
        server.DATA_DIR = root / "data"
        server.WORKSPACE_DIR = root / "workspace"
        server.DB_PATH = server.DATA_DIR / "career_copilot.sqlite"
        server.PROFILE_PATH = server.DATA_DIR / "profile.json"
        server.USER_CONTEXT_PATH = server.DATA_DIR / "user_context.json"
        server.APPLY_ASSIST_DIR = server.DATA_DIR / "apply-assist"
        server.BROWSER_PROFILE_DIR = server.DATA_DIR / "browser-profile"
        server.RESUME_UPLOAD_DIR = server.DATA_DIR / "resumes"
        server.setup_db()

    def tearDown(self) -> None:
        server.SCAN_THREADS.clear()
        for key, value in self.old_paths.items():
            setattr(server, key, value)
        self.tmp.cleanup()


class ParserTests(unittest.TestCase):
    def fixture(self, name: str) -> str:
        return (FIXTURES / name).read_text(encoding="utf-8")

    def test_parse_linkedin_fixture(self):
        jobs = server.parse_linkedin_jobs_from_html(self.fixture("linkedin.html"), "product design intern", 5)
        self.assertEqual(jobs[0]["external_job_id"], "4411111111")
        self.assertEqual(server.canonical_job_url("LinkedIn", jobs[0]["url"], jobs[0]["external_job_id"]), "https://www.linkedin.com/jobs/view/4411111111")

    def test_parse_internsg_fixture(self):
        jobs = server.parse_internsg_jobs_from_html(self.fixture("internsg.html"), "product design intern", 5)
        self.assertEqual(jobs[0]["source"], "InternSG")
        self.assertIn("Product Design", jobs[0]["position"])

    def test_parse_indeed_fixture(self):
        jobs = server.parse_indeed_jobs_from_html(self.fixture("indeed.html"), "ux research intern", 5)
        self.assertEqual(jobs[0]["url"], "https://sg.indeed.com/viewjob?jk=abc123def456")
        self.assertEqual(jobs[0]["company"], "Research Co")

    def test_parse_jobstreet_fixture(self):
        jobs = server.parse_jobstreet_jobs_from_html(self.fixture("jobstreet.html"), "ui ux intern", 5)
        self.assertEqual(jobs[0]["source"], "JobStreet")
        self.assertEqual(jobs[0]["url"], "https://sg.jobstreet.com/job/98765432")
        self.assertIn("UI/UX", jobs[0]["position"])

    def test_job_metadata_detects_employment_conversion_and_salary(self):
        metadata = server.job_metadata(
            "AI Product Intern",
            "Monthly stipend SGD 1,200 - 1,800. Strong interns may receive a full-time conversion offer.",
            "Internship",
            "SG",
        )
        self.assertEqual(metadata["employment_type"], "Internship")
        self.assertEqual(metadata["conversion_opportunity"], 1)
        self.assertEqual(metadata["salary_currency"], "SGD")
        self.assertEqual(metadata["salary_period"], "monthly")
        self.assertEqual(metadata["salary_min"], 1200)
        self.assertEqual(metadata["salary_max"], 1800)
        self.assertEqual(server.detect_employment_type("Graduate Product Designer"), "Graduate")
        self.assertEqual(server.detect_employment_type("Full-time UX Designer"), "Full-time")
        self.assertEqual(server.detect_employment_type("Contract UX Researcher"), "Contract")


class DailyRunTests(TempAppMixin, unittest.TestCase):
    def test_daily_run_once_and_force(self):
        calls = []

        def fake_scan_sources(triggered_by="manual", forced=True, scan_run_id=None, region=None):
            run_id = scan_run_id or server.create_scan_run(triggered_by, forced, region)
            server.finish_scan_run(run_id, "success", 1, 1, 1, 0, [])
            calls.append((triggered_by, forced, region))
            return {
                "run_id": run_id,
                "status": "success",
                "scanned": 1,
                "saved": 1,
                "recommended": 1,
                "ai_recommended": 0,
                "source_counts": {"Fixture": 1},
                "failures": [],
            }

        with mock.patch.object(server, "scan_sources", fake_scan_sources):
            first = server.run_daily_scan(force=False, triggered_by="auto_open")
            second = server.run_daily_scan(force=False, triggered_by="auto_open")
            third = server.run_daily_scan(force=True, triggered_by="manual")

        self.assertFalse(first["skipped"])
        self.assertTrue(second["skipped"])
        self.assertFalse(third["skipped"])
        self.assertEqual(len(calls), 2)


class RecommendationTests(TempAppMixin, unittest.TestCase):
    def test_applied_dropped_and_hard_flags_do_not_recommend(self):
        good = server.upsert_job(
            {
                "company": "Good Co",
                "position": "Product Design Intern",
                "source": "JobStreet",
                "url": "https://sg.jobstreet.com/job/111",
                "jd_text": "Singapore product design intern UX research service design Figma prototype AI product.",
            }
        )
        blocked = server.upsert_job(
            {
                "company": "Blocked Co",
                "position": "UX Intern",
                "source": "InternSG",
                "url": "https://www.internsg.com/job/blocked/",
                "jd_text": "Singapore citizens only. UX research intern service design.",
            }
        )
        dropped = server.upsert_job(
            {
                "company": "Dropped Co",
                "position": "Product Management Intern",
                "source": "LinkedIn",
                "url": "https://www.linkedin.com/jobs/view/999999999",
                "jd_text": "Singapore product management intern product operations AI design research.",
            }
        )
        server.set_decision(good["id"], "Apply")
        server.set_decision(dropped["id"], "Drop")

        self.assertFalse(server.is_recommendation_available(server.get_job(good["id"])))
        self.assertFalse(server.is_recommendation_available(server.get_job(dropped["id"])))
        self.assertIn("citizen_or_pr_only", server.get_job(blocked["id"])["eligibility_flags"])
        self.assertFalse(server.is_recommendation_available(server.get_job(blocked["id"])))

    def test_low_salary_soft_preference_does_not_hide_strong_match(self):
        server.save_user_context(
            {
                "active_region": "SG",
                "context": {
                    "employment_priority": "internship",
                    "salary_currency": "SGD",
                    "salary_period": "monthly",
                    "salary_min": 1800,
                    "salary_preferred": 2200,
                    "target_directions": ["ai-product"],
                },
            }
        )
        job = server.upsert_job(
            {
                "company": "Stipend Co",
                "position": "AI Product Intern",
                "source": "JobStreet",
                "url": "https://sg.jobstreet.com/job/salary-soft",
                "jd_text": "Singapore AI product intern LLM UX research workflow automation. Stipend SGD 1,000 per month.",
            }
        )
        with server.get_db() as conn:
            conn.execute("update jobs set score=4.4, status='Recommended' where id=?", (job["id"],))

        recommendations = server.list_today_recommendations({"limit": ["20"]})["jobs"]
        ranked = next(item for item in recommendations if item["id"] == job["id"])
        self.assertEqual(ranked["salary_fit"], "low")
        self.assertIn("薪资偏低", ranked["salary_fit_label"])
        self.assertIn(job["id"], [item["id"] for item in recommendations])


class MultiRegionTests(TempAppMixin, unittest.TestCase):
    def test_profile_options_follow_region_currency_and_choices(self):
        sg_options = server.profile_options_payload("SG")
        cn_options = server.profile_options_payload("CN")
        hk_options = server.profile_options_payload("HK")

        self.assertEqual(sg_options["salary_currency"], "SGD")
        self.assertEqual(cn_options["salary_currency"], "CNY")
        self.assertEqual(hk_options["salary_currency"], "HKD")
        self.assertFalse(sg_options["city_required"])
        self.assertTrue(cn_options["city_required"])
        self.assertIn("Student Pass", [item["value"] for item in sg_options["work_authorisation_options"]])
        self.assertIn("ai-product", [item["value"] for item in sg_options["direction_options"]])
        self.assertIn("AI 与产品", [item["category"] for item in sg_options["direction_options"]])
        self.assertIn("monthly", sg_options["salary_band_options"])

    def test_singapore_company_catalog_has_new_radar_fields(self):
        catalog = server.company_catalog("SG")
        by_company = {item["company"]: item for item in catalog}

        for company in ["IKEA Singapore", "foodpanda Singapore", "POP MART Singapore", "Changi Airport Group", "PatSnap", "Hypotenuse AI", "WIZ.AI", "ADVANCE.AI"]:
            self.assertIn(company, by_company)
            self.assertTrue(by_company[company].get("recommend_reason"))
            self.assertTrue(by_company[company].get("tags"))

        self.assertIn("中文友好概率较高", by_company["POP MART Singapore"]["tags"])

    def test_user_context_catalog_and_watchlist_crud(self):
        regions = server.regions_payload()
        self.assertEqual(regions["active_region"], "SG")
        self.assertIn("CN", [item["code"] for item in regions["regions"]])

        context = server.save_user_context(
            {
                "active_region": "HK",
                "context": {
                    "city": "Hong Kong",
                    "work_authorisation": "HK work eligibility",
                    "target_directions": ["ux-product-design"],
                    "job_types": ["Internship"],
                },
                "onboarding_completed": True,
            }
        )
        self.assertEqual(context["active_region"], "HK")
        self.assertTrue(context["onboarding_completed"])
        self.assertTrue(server.company_catalog("HK"))

        added = server.add_watch_company(
            {
                "region": "HK",
                "company": "Test HK Co",
                "url": "https://example.com/careers",
                "focus": "UX and product internships",
            }
        )
        self.assertEqual(added["region"], "HK")
        self.assertEqual(server.watchlist("HK")[0]["company"], "Test HK Co")

        updated = server.update_watch_company(added["id"], {"focus": "UX research internships", "priority": 99})
        self.assertEqual(updated["focus"], "UX research internships")

        server.delete_watch_company(added["id"])
        self.assertFalse([item for item in server.watchlist("HK") if item["company"] == "Test HK Co"])

    def test_active_region_filters_recommendations_and_company_boosts(self):
        server.save_user_context({"active_region": "CN", "context": {"city": "Shanghai"}})
        server.add_watch_company(
            {
                "region": "CN",
                "company": "ByteDance",
                "url": "https://jobs.bytedance.com/en/position",
                "focus": "AI product internships",
                "priority": 95,
            }
        )
        sg_job = server.upsert_job(
            {
                "region": "SG",
                "company": "Singapore Co",
                "position": "AI Product Intern",
                "source": "JobStreet",
                "url": "https://sg.jobstreet.com/job/region-test",
                "jd_text": "Singapore AI product intern LLM UX research service design.",
            }
        )
        cn_job = server.upsert_job(
            {
                "region": "CN",
                "city": "Shanghai",
                "company": "ByteDance",
                "position": "AI Product Intern",
                "source": "Company Site",
                "url": "https://jobs.bytedance.com/en/position/region-test",
                "jd_text": "Shanghai AI product intern LLM UX research service design.",
            }
        )
        with server.get_db() as conn:
            conn.execute("update jobs set score=4.5, status='Recommended' where id=?", (sg_job["id"],))
            conn.execute("update jobs set score=3.2, status='Recommended' where id=?", (cn_job["id"],))

        recommendations = server.list_today_recommendations({"limit": ["20"]})
        ids = [job["id"] for job in recommendations["jobs"]]
        self.assertIn(cn_job["id"], ids)
        self.assertNotIn(sg_job["id"], ids)
        boosted = next(job for job in recommendations["jobs"] if job["id"] == cn_job["id"])
        self.assertGreater(boosted["company_boost"], 0)
        self.assertEqual(boosted["region_fit"], 1.0)

    def test_company_catalog_marks_current_city_match(self):
        server.save_user_context({"active_region": "CN", "context": {"city": "Shanghai"}})
        catalog = server.company_catalog("CN", "Shanghai")
        shanghai_companies = [item for item in catalog if "Shanghai" in item.get("city_tags", [])]

        self.assertTrue(shanghai_companies)
        self.assertTrue(all(item["city_match"] for item in shanghai_companies[:2]))


class CareerFitTests(TempAppMixin, unittest.TestCase):
    def sample_resume_text(self) -> str:
        return (
            "Sample Candidate\n"
            "Human-centred service design, UX research, service blueprint, Figma prototyping.\n"
            "Used AI-assisted research synthesis, prompt-based ideation, scenario exploration, "
            "JD/capability matching, and workflow automation for product design projects."
        )

    def pdf_bytes(self, text: str) -> bytes:
        from reportlab.pdfgen import canvas

        buffer = io.BytesIO()
        page = canvas.Canvas(buffer)
        page.drawString(72, 760, text[:100])
        page.save()
        return buffer.getvalue()

    def docx_bytes(self, text: str) -> bytes:
        from docx import Document

        buffer = io.BytesIO()
        doc = Document()
        doc.add_paragraph(text)
        doc.save(buffer)
        return buffer.getvalue()

    def test_resume_upload_parses_pdf_docx_and_md(self):
        md = server.save_uploaded_resume("yan-resume.md", self.sample_resume_text().encode("utf-8"), "text/markdown")
        self.assertIn("AI Product", [item["label"] for item in md["analysis"]["directions"][:3]])
        self.assertTrue(Path(md["resume"]["text_path"]).exists())
        user_context = server.load_user_context()
        self.assertTrue(user_context["resume_analyzed"])
        self.assertEqual(user_context["onboarding_step"], 3)

        pdf = server.save_uploaded_resume("yan-resume.pdf", self.pdf_bytes(self.sample_resume_text()), "application/pdf")
        self.assertEqual(pdf["resume"]["original_filename"], "yan-resume.pdf")

        docx = server.save_uploaded_resume(
            "yan-resume.docx",
            self.docx_bytes(self.sample_resume_text()),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        self.assertEqual(server.get_active_resume_version()["id"], docx["resume"]["id"])
        self.assertIn("docx", server.load_profile()["resume_path"].lower())

    def test_bad_resume_upload_is_friendly(self):
        with self.assertRaisesRegex(ValueError, "PDF, DOCX, MD, or TXT"):
            server.save_uploaded_resume("resume.png", b"not a resume", "image/png")

    def test_preferences_reorder_recommendations_without_bypassing_rules(self):
        server.save_uploaded_resume("yan-resume.md", self.sample_resume_text().encode("utf-8"), "text/markdown")
        ai_job = server.upsert_job(
            {
                "company": "Agent Co",
                "position": "AI Product Intern",
                "source": "JobStreet",
                "url": "https://sg.jobstreet.com/job/222",
                "jd_text": "Singapore AI product intern LLM chatbot workflow automation.",
            }
        )
        service_job = server.upsert_job(
            {
                "company": "Service Co",
                "position": "Service Design Intern",
                "source": "InternSG",
                "url": "https://www.internsg.com/job/service/",
                "jd_text": "Singapore service design intern service blueprint user journey.",
            }
        )
        blocked = server.upsert_job(
            {
                "company": "Blocked Co",
                "position": "AI Product Intern",
                "source": "LinkedIn",
                "url": "https://www.linkedin.com/jobs/view/1234567",
                "jd_text": "Singapore citizens only. AI product intern LLM.",
            }
        )
        with server.get_db() as conn:
            conn.execute("update jobs set score=3.2, status='Recommended' where id in (?, ?)", (ai_job["id"], service_job["id"]))
        server.save_career_preferences({"selected_directions": ["ai-product"]})
        recommendations = server.list_today_recommendations({"limit": ["20"]})["jobs"]
        self.assertEqual(recommendations[0]["id"], ai_job["id"])
        self.assertGreater(recommendations[0]["preference_boost"], 0)
        self.assertNotIn(blocked["id"], [job["id"] for job in recommendations])


class AsyncScanTests(TempAppMixin, unittest.TestCase):
    def test_scan_sources_merge_ai_queries_without_ai_visual_rows(self):
        sources = server.expected_scan_sources("SG")
        self.assertIn("LinkedIn（含 AI 关键词）", sources)
        self.assertIn("InternSG（含 AI 关键词）", sources)
        self.assertNotIn("LinkedIn AI", sources)
        self.assertNotIn("InternSG AI", sources)

        calls = []

        def fake_linkedin(limit, queries=None, region=None):
            calls.append(queries)
            return [], []

        with mock.patch.object(server, "fetch_linkedin_jobs", fake_linkedin):
            fetcher = server.scan_source_definitions("SG")[0][1]
            fetcher(5)

        self.assertTrue(any(query is None for query in calls))
        self.assertTrue(any(isinstance(query, list) and any("ai" in item.lower() for item in query) for query in calls))

    def test_scan_source_details_mark_supplemental_sources(self):
        details = {item["source"]: item["mode"] for item in server.expected_scan_source_details("SG")}

        self.assertEqual(details["LinkedIn（含 AI 关键词）"], "primary")
        self.assertEqual(details["InternSG（含 AI 关键词）"], "primary")
        self.assertEqual(details["Indeed"], "supplemental")
        self.assertEqual(details["JobStreet"], "supplemental")
        self.assertEqual(details["公司官网"], "company")

    def test_limited_source_failure_keeps_scan_partial_when_other_sources_save(self):
        def good_source(limit):
            return [
                {
                    "company": "Good Scan Co",
                    "position": "AI Product Intern",
                    "source": "InternSG",
                    "url": "https://www.internsg.com/job/good-scan/",
                    "jd_text": "Singapore AI product intern UX research service design.",
                }
            ], []

        def limited_source(limit):
            return [], ["Indeed 受限：连续失败较多，已跳过剩余查询。"]

        with (
            mock.patch.object(
                server,
                "scan_source_definitions",
                return_value=[
                    ("InternSG（含 AI 关键词）", good_source, 1),
                    ("Indeed", limited_source, 1),
                ],
            ),
            mock.patch.object(server, "generate_report"),
        ):
            result = server.scan_sources(region="SG")

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["saved"], 1)
        source_statuses = {item["source"]: item["status"] for item in result["scan_run"]["sources"]}
        self.assertEqual(source_statuses["Indeed"], "limited")

    def test_async_scan_returns_running_run_and_finishes(self):
        def fake_scan_sources(triggered_by="manual", forced=True, scan_run_id=None, region=None):
            source_run_id = server.create_scan_source_run(scan_run_id, "Fixture")
            time.sleep(0.08)
            server.finish_scan_source_run(source_run_id, "success", 2, 2, [])
            server.finish_scan_run(scan_run_id, "success", 2, 2, 1, 0, [])
            return {
                "run_id": scan_run_id,
                "status": "success",
                "scanned": 2,
                "saved": 2,
                "recommended": 1,
                "ai_recommended": 0,
                "source_counts": {"Fixture": 2},
                "failures": [],
            }

        with mock.patch.object(server, "scan_sources", fake_scan_sources):
            started = server.start_scan_async(triggered_by="manual", forced=True)
            self.assertTrue(started["started"])
            self.assertTrue(started["running"])
            run_id = started["run"]["id"]
            thread = server.SCAN_THREADS.get(run_id)
            self.assertIsNotNone(thread)
            thread.join(timeout=1)

        payload = server.scan_status_payload(run_id)
        self.assertFalse(payload["running"])
        self.assertEqual(payload["run"]["status"], "success")
        self.assertEqual(payload["run"]["sources"][0]["source"], "Fixture")

    def test_stale_running_scan_is_interrupted_before_new_scan(self):
        stale_run_id = server.create_scan_run("manual", True, "SG")
        server.create_scan_source_run(stale_run_id, "InternSG")

        def fake_scan_sources(triggered_by="manual", forced=True, scan_run_id=None, region=None):
            server.finish_scan_run(scan_run_id, "success", 0, 0, 0, 0, [])
            return {
                "run_id": scan_run_id,
                "status": "success",
                "scanned": 0,
                "saved": 0,
                "recommended": 0,
                "ai_recommended": 0,
                "source_counts": {},
                "failures": [],
            }

        with mock.patch.object(server, "scan_sources", fake_scan_sources):
            started = server.start_scan_async(triggered_by="manual", forced=True, region="SG")
            self.assertTrue(started["started"])
            thread = server.SCAN_THREADS.get(started["run"]["id"])
            if thread:
                thread.join(timeout=1)

        stale = server.get_scan_run(stale_run_id)
        self.assertEqual(stale["status"], "interrupted")
        self.assertEqual(stale["sources"][0]["status"], "interrupted")


class ApplyAssistTests(TempAppMixin, unittest.TestCase):
    def test_unsupported_source_opens_manual_and_records_questions(self):
        job = server.upsert_job(
            {
                "company": "Manual Co",
                "position": "Service Design Intern",
                "source": "Company Site",
                "url": "https://example.com/job",
                "jd_text": "Singapore service design intern user research prototype.",
            }
        )
        server.set_decision(job["id"], "Apply")
        with mock.patch.object(webbrowser, "open") as open_mock:
            result = server.apply_assist(job["id"])
        open_mock.assert_called_once_with("https://example.com/job")
        self.assertEqual(result["status"], "opened_manual")
        application = server.get_application(job["id"])
        self.assertEqual(application["assist_status"], "opened_manual")
        self.assertTrue(application["custom_questions_json"])

    @unittest.skipUnless(importlib.util.find_spec("playwright"), "Playwright is not installed")
    def test_playwright_dependency_available_for_browser_assist(self):
        self.assertIsNotNone(importlib.util.find_spec("playwright"))

    @unittest.skipUnless(importlib.util.find_spec("playwright"), "Playwright is not installed")
    def test_browser_assist_fills_mock_form_without_submitting(self):
        root = Path(self.tmp.name)
        resume = root / "resume.pdf"
        cover = root / "cover.pdf"
        resume.write_text("resume", encoding="utf-8")
        cover.write_text("cover", encoding="utf-8")
        form = root / "mock-form.html"
        form.write_text(
            """
            <!doctype html>
            <html>
              <body>
                <button type="button">Apply</button>
                <form onsubmit="window.submitted = true; return false;">
                  <label>First name<input aria-label="First name"></label>
                  <label>Last name<input aria-label="Last name"></label>
                  <label>Email<input aria-label="Email" type="email"></label>
                  <label>Phone<input aria-label="Phone"></label>
                  <label>Resume upload<input aria-label="Resume upload" type="file"></label>
                  <label>Tell us why you fit<textarea aria-label="Tell us why you fit"></textarea></label>
                  <button type="submit">Submit application</button>
                </form>
              </body>
            </html>
            """,
            encoding="utf-8",
        )
        result_path = root / "result.json"
        payload_path = root / "payload.json"
        payload_path.write_text(
            json.dumps(
                {
                    "job": {
                        "id": 1,
                        "url": form.as_uri(),
                        "resume_path": str(resume),
                        "cover_letter_path": str(cover),
                    },
                    "profile": {
                        "first_name": "Yangtai",
                        "last_name": "Yan",
                        "email": "yan@example.com",
                        "phone": "+65 9000 0000",
                    },
                    "browser_profile_dir": str(root / "browser-profile"),
                    "result_path": str(result_path),
                    "headless": True,
                    "keep_open": False,
                }
            ),
            encoding="utf-8",
        )
        script = Path(server.APP_DIR) / "scripts" / "browser_apply_assist.py"
        completed = subprocess.run([sys.executable, str(script), str(payload_path)], cwd=server.APP_DIR, timeout=90)
        self.assertEqual(completed.returncode, 0)
        result = json.loads(result_path.read_text(encoding="utf-8"))
        self.assertFalse(result["submitted"])
        self.assertIn("email", result["filled_fields"])
        self.assertTrue(result["uploaded_files"])
        self.assertTrue(result["open_questions"])


if __name__ == "__main__":
    unittest.main()

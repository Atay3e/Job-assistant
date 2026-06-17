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


class MultiRegionTests(TempAppMixin, unittest.TestCase):
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

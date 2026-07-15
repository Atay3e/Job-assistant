from __future__ import annotations

import importlib.util
import gzip
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
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
        self.old_env = {key: os.environ.get(key) for key in [
            "JOB_ASSISTANT_REQUIRE_AUTH",
            "JOB_ASSISTANT_CLOUD_STATE",
            "SUPABASE_URL",
            "SUPABASE_ANON_KEY",
            "SUPABASE_PUBLISHABLE_KEY",
            "SUPABASE_SERVICE_ROLE_KEY",
            "SUPABASE_SECRET_KEY",
            "SUPABASE_STORAGE_BUCKET",
        ]}
        for key in self.old_env:
            os.environ.pop(key, None)
        server.DATA_DIR = root / "data"
        server.WORKSPACE_DIR = root / "workspace"
        server.DB_PATH = server.DATA_DIR / "career_copilot.sqlite"
        server.PROFILE_PATH = server.DATA_DIR / "profile.json"
        server.USER_CONTEXT_PATH = server.DATA_DIR / "user_context.json"
        server.APPLY_ASSIST_DIR = server.DATA_DIR / "apply-assist"
        server.BROWSER_PROFILE_DIR = server.DATA_DIR / "browser-profile"
        server.RESUME_UPLOAD_DIR = server.DATA_DIR / "resumes"
        server.INITIALIZED_DB_PATHS.clear()
        server.CLOUD_STATE_LOADED.clear()
        server.CLOUD_STATE_BUCKET_READY.clear()
        server.CLOUD_STATE_USER_LOCKS.clear()
        server.setup_db()

    def tearDown(self) -> None:
        server.SCAN_THREADS.clear()
        server.INITIALIZED_DB_PATHS.clear()
        server.CLOUD_STATE_LOADED.clear()
        server.CLOUD_STATE_BUCKET_READY.clear()
        server.CLOUD_STATE_USER_LOCKS.clear()
        for key, value in self.old_paths.items():
            setattr(server, key, value)
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()


class MultiUserStorageTests(TempAppMixin, unittest.TestCase):
    def test_user_context_is_scoped_by_user(self):
        with server.request_user_context("user-a"):
            server.setup_db()
            server.save_user_context({"active_region": "CN", "context": {"city": "Shanghai"}})

        with server.request_user_context("user-b"):
            server.setup_db()
            context_b = server.load_user_context()

        with server.request_user_context("user-a"):
            context_a = server.load_user_context()

        self.assertEqual(context_a["active_region"], "CN")
        self.assertEqual(context_a["contexts"]["CN"]["city"], "Shanghai")
        self.assertEqual(context_b["active_region"], "SG")

    def test_jobs_are_scoped_by_user(self):
        with server.request_user_context("user-a"):
            server.setup_db()
            server.upsert_job(
                {
                    "company": "Scoped Co",
                    "position": "Product Design Intern",
                    "source": "Manual",
                    "url": "https://example.com/scoped-a",
                    "jd_text": "Singapore product design internship.",
                }
            )
            jobs_a = server.list_jobs({})

        with server.request_user_context("user-b"):
            server.setup_db()
            jobs_b = server.list_jobs({})

        self.assertEqual(len([job for job in jobs_a if job["company"] == "Scoped Co"]), 1)
        self.assertEqual(len([job for job in jobs_b if job["company"] == "Scoped Co"]), 0)

    def test_user_state_archive_restores_private_files_and_excludes_browser_profile(self):
        with server.request_user_context("cloud-user"):
            server.setup_db()
            resume_file = server.current_resume_upload_dir() / "resume.txt"
            resume_file.parent.mkdir(parents=True, exist_ok=True)
            resume_file.write_text("resume body", encoding="utf-8")
            workspace_file = server.current_workspace_dir() / "applications" / "draft.txt"
            workspace_file.parent.mkdir(parents=True, exist_ok=True)
            workspace_file.write_text("draft body", encoding="utf-8")
            browser_secret = server.current_browser_profile_dir() / "cookies.txt"
            browser_secret.parent.mkdir(parents=True, exist_ok=True)
            browser_secret.write_text("do not upload", encoding="utf-8")

            archive = server.build_user_state_archive()
            shutil.rmtree(server.current_data_dir())
            shutil.rmtree(server.current_workspace_dir())
            restored = server.restore_user_state_archive(archive)

            self.assertTrue(restored)
            self.assertEqual(resume_file.read_text(encoding="utf-8"), "resume body")
            self.assertEqual(workspace_file.read_text(encoding="utf-8"), "draft body")
            self.assertFalse(browser_secret.exists())

    def test_cloud_state_sync_uploads_and_restores_user_state(self):
        storage: dict[str, bytes] = {}
        bucket_created = {"value": False}

        def fake_storage_request(method, path, data=None, headers=None, tolerate_404=False):
            if path == "/bucket" and method == "POST":
                bucket_created["value"] = True
                return 200, b"{}"
            if path.startswith("/bucket/"):
                if method == "GET":
                    if bucket_created["value"]:
                        return 200, b"{}"
                    if tolerate_404:
                        return 404, b"{}"
            if "/object/" in path:
                object_path = path.split("/object/", 1)[1]
                if method == "GET":
                    if object_path in storage:
                        return 200, storage[object_path]
                    if tolerate_404:
                        return 404, b"{}"
                if method == "POST":
                    storage[object_path] = data or b""
                    return 200, b"{}"
            raise AssertionError(f"unexpected storage request: {method} {path}")

        with mock.patch.dict(
            os.environ,
            {
                "JOB_ASSISTANT_CLOUD_STATE": "1",
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SERVICE_ROLE_KEY": "service.jwt.token",
                "SUPABASE_STORAGE_BUCKET": "job-assistant-users",
            },
            clear=False,
        ), mock.patch.object(server, "supabase_storage_request", side_effect=fake_storage_request):
            with server.request_user_context("roundtrip-user"):
                server.setup_db()
                server.save_user_context({"active_region": "CN", "context": {"city": "Shanghai"}})
                job = server.upsert_job(
                    {
                        "company": "Roundtrip Co",
                        "position": "UX Intern",
                        "source": "Manual",
                        "url": "https://example.com/roundtrip",
                        "jd_text": "Shanghai UX internship.",
                        "region": "CN",
                        "city": "Shanghai",
                    }
                )
                self.assertTrue(server.sync_cloud_state("test"))
                self.assertTrue(any(key.endswith("roundtrip-user/state.zip") for key in storage))

                shutil.rmtree(server.current_data_dir())
                shutil.rmtree(server.current_workspace_dir())
                server.CLOUD_STATE_LOADED.clear()
                server.INITIALIZED_DB_PATHS.clear()

                restored_context = server.load_user_context()
                restored_jobs = server.list_jobs({})

            self.assertEqual(restored_context["active_region"], "CN")
            self.assertEqual(restored_context["contexts"]["CN"]["city"], "Shanghai")
            self.assertTrue(any(item["url"] == job["url"] for item in restored_jobs))


class SupabaseSetupScriptTests(unittest.TestCase):
    def test_new_supabase_key_names_are_mapped_to_runtime_env(self):
        from scripts import configure_render_supabase as setup

        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env.supabase.local"
            env_file.write_text(
                "\n".join(
                    [
                        "SUPABASE_URL=https://example.supabase.co",
                        "SUPABASE_PUBLISHABLE_KEY=sb_publishable_test",
                        "SUPABASE_SECRET_KEY=sb_secret_test",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with mock.patch.object(setup.urllib.request, "urlopen", return_value=FakeResponse()):
                values = setup.load_env(env_file)

        self.assertEqual(values["SUPABASE_ANON_KEY"], "sb_publishable_test")
        self.assertEqual(values["SUPABASE_SERVICE_ROLE_KEY"], "sb_secret_test")
        self.assertEqual(values["JOB_ASSISTANT_REQUIRE_AUTH"], "1")


class SupabaseStorageTests(unittest.TestCase):
    def test_storage_bucket_missing_400_body_is_treated_as_404(self):
        error = server.urllib.error.HTTPError(
            "https://example.supabase.co/storage/v1/bucket/missing",
            400,
            "Bad Request",
            {},
            io.BytesIO(b'{"statusCode":"404","error":"Bucket not found","message":"Bucket not found"}'),
        )
        with mock.patch.dict(
            os.environ,
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SERVICE_ROLE_KEY": "service.jwt.token",
            },
            clear=False,
        ), mock.patch.object(server.urllib.request, "urlopen", side_effect=error):
            status, payload = server.supabase_storage_request("GET", "/bucket/missing", tolerate_404=True)

        self.assertEqual(status, 404)
        self.assertIn(b"Bucket not found", payload)


class AuthTests(unittest.TestCase):
    def test_bearer_token_can_be_verified_through_supabase_auth_without_jwt_secret(self):
        class Handler:
            headers = {"Authorization": "Bearer token-123"}

        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b'{"id":"user-123"}'

        with mock.patch.dict(
            os.environ,
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_ANON_KEY": "anon-key",
                "SUPABASE_JWT_SECRET": "",
            },
            clear=False,
        ), mock.patch.object(server.urllib.request, "urlopen", return_value=Response()) as urlopen_mock:
            self.assertEqual(server.user_id_from_bearer_token(Handler()), "user-123")

        request = urlopen_mock.call_args.args[0]
        self.assertEqual(request.full_url, "https://example.supabase.co/auth/v1/user")


class ParserTests(unittest.TestCase):
    def fixture(self, name: str) -> str:
        return (FIXTURES / name).read_text(encoding="utf-8")

    def test_json_response_compresses_large_payloads_for_supported_clients(self):
        class Handler:
            headers = {"Accept-Encoding": "gzip, deflate"}

            def __init__(self):
                self.response_headers = {}
                self.wfile = io.BytesIO()

            def send_response(self, status):
                self.status = status

            def send_header(self, name, value):
                self.response_headers[name] = value

            def end_headers(self):
                pass

        handler = Handler()
        payload = {"jobs": [{"name": "Product Intern", "company": "Example"}] * 100}
        server.json_response(handler, payload)

        self.assertEqual(handler.response_headers["Content-Encoding"], "gzip")
        self.assertEqual(json.loads(gzip.decompress(handler.wfile.getvalue())), payload)
        self.assertEqual(int(handler.response_headers["Content-Length"]), len(handler.wfile.getvalue()))

    def test_keyword_matching_preserves_word_boundaries(self):
        self.assertTrue(server.has_keyword("ai-driven product work", "ai"))
        self.assertTrue(server.has_keyword("use ai for research", "ai"))
        self.assertFalse(server.has_keyword("paid internship", "ai"))
        self.assertFalse(server.has_keyword("ai_research", "ai"))
        self.assertTrue(server.has_keyword("研究 ai 产品", "ai"))

    def test_application_deadline_parser_accepts_explicit_dates_only(self):
        self.assertEqual(
            server.extract_application_deadline("Applications close 31 July 2026"),
            "2026-07-31",
        )
        self.assertEqual(
            server.extract_application_deadline("Closing date: 07 Aug 2026"),
            "2026-08-07",
        )
        self.assertEqual(
            server.extract_application_deadline("Apply by 2026-09-18"),
            "2026-09-18",
        )
        self.assertEqual(server.extract_application_deadline("Able to meet tight deadlines."), "")
        self.assertEqual(server.extract_application_deadline("Application deadline: September 18, 2359"), "")

    def test_application_deadline_status_is_actionable(self):
        reference = server.dt.date(2026, 7, 14)

        self.assertEqual(server.application_deadline_status("2026-07-14", reference)["code"], "today")
        self.assertEqual(server.application_deadline_status("2026-07-16", reference)["code"], "urgent")
        self.assertEqual(server.application_deadline_status("2026-07-20", reference)["code"], "soon")
        self.assertEqual(server.application_deadline_status("2026-07-13", reference)["code"], "expired")
        self.assertEqual(server.application_deadline_status("", reference)["code"], "unknown")

    def test_queue_sort_puts_live_urgent_deadlines_first_and_expired_last(self):
        reference = server.dt.date(2026, 7, 14)
        jobs = [
            {"id": 1, "application_deadline": "", "rank_score": 4.9, "updated_at": "2026-07-14T12:00:00"},
            {"id": 2, "application_deadline": "2026-07-16", "rank_score": 3.5, "updated_at": "2026-07-10T12:00:00"},
            {"id": 3, "application_deadline": "2026-07-13", "rank_score": 5.0, "updated_at": "2026-07-14T13:00:00"},
        ]

        ordered = sorted(jobs, key=lambda job: server.queue_job_sort_key(job, reference))

        self.assertEqual([job["id"] for job in ordered], [2, 1, 3])

    def test_queue_decision_separates_today_next_and_review(self):
        reference = server.dt.date(2026, 7, 14)
        today_job = {"fit_score": 4.4, "updated_at": "2026-07-14T09:00:00"}
        next_job = {"fit_score": 3.6, "updated_at": "2026-07-14T09:00:00"}
        muted_job = {
            "fit_score": 4.8,
            "user_tag_mutes": [{"id": "software_engineering", "label": "软件工程"}],
            "updated_at": "2026-07-14T09:00:00",
        }
        mismatched_job = {
            "fit_score": 4.8,
            "direction_mismatch_adjustment": -0.55,
            "updated_at": "2026-07-14T09:00:00",
        }

        self.assertEqual(server.queue_decision(today_job, reference)["priority"], "today")
        self.assertEqual(server.queue_decision(next_job, reference)["priority"], "next")
        self.assertEqual(server.queue_decision(muted_job, reference)["priority"], "review")
        self.assertEqual(server.queue_decision(mismatched_job, reference)["priority"], "review")

    def test_followup_decision_separates_due_waiting_and_archive(self):
        reference = server.dt.date(2026, 7, 15)
        due = {"status": "Applied", "applied_date": "2026-07-08", "followup_count": 0}
        waiting = {
            "status": "Applied",
            "applied_date": "2026-07-01",
            "last_followup_at": "2026-07-12",
            "followup_count": 1,
        }
        archive = {
            "status": "Applied",
            "applied_date": "2026-06-20",
            "last_followup_at": "2026-07-07",
            "followup_count": 2,
        }

        self.assertEqual(server.followup_decision(due, reference)["priority"], "followup")
        self.assertEqual(server.followup_decision(waiting, reference)["priority"], "waiting")
        self.assertEqual(server.followup_decision(archive, reference)["priority"], "archive")

    def test_ranked_applied_job_exposes_one_followup_decision_to_the_ui(self):
        applied_date = (server.dt.date.today() - server.dt.timedelta(days=7)).strftime(server.DATE_FMT)
        ranked = server.rank_job_with_preferences(
            {
                "company": "Followup Product Co",
                "position": "Product Design Intern",
                "status": "Applied",
                "applied_date": applied_date,
                "score": 4.0,
                "region": "SG",
            },
            [],
            {},
            "SG",
        )

        self.assertEqual(ranked["followup_priority"], "followup")
        self.assertEqual(ranked["followup_priority_label"], "今天跟进")
        self.assertIn("跟进", ranked["followup_reason"])

    def test_parse_linkedin_fixture(self):
        jobs = server.parse_linkedin_jobs_from_html(self.fixture("linkedin.html"), "product design intern", 5)
        self.assertEqual(jobs[0]["external_job_id"], "4411111111")
        self.assertEqual(server.canonical_job_url("LinkedIn", jobs[0]["url"], jobs[0]["external_job_id"]), "https://www.linkedin.com/jobs/view/4411111111")

    def test_parse_linkedin_public_detail_extracts_job_description(self):
        html = """
        <section>
          <div class="show-more-less-html__markup show-more-less-html__markup--clamp-after-5">
            <strong>About the role</strong><br>
            Join our Singapore product internship and work directly with founders.
            Potential for full-time employment after your internship, with a monthly stipend.
            You will conduct user research, prototype in Figma, and evaluate AI workflows.
          </div>
        </section>
        """

        detail = server.parse_linkedin_public_detail_html(html)

        self.assertIn("Potential for full-time employment", detail)
        self.assertIn("user research", detail)

    def test_parse_internsg_fixture(self):
        jobs = server.parse_internsg_jobs_from_html(self.fixture("internsg.html"), "product design intern", 5)
        self.assertEqual(jobs[0]["source"], "InternSG")
        self.assertIn("Product Design", jobs[0]["position"])

    def test_parse_internsg_removes_featured_label_from_company(self):
        html = """
        <div class="ast-row list-featured">
          <div class="ast-col-lg-3">Orfeostory Pte Ltd Featured</div>
          <div class="ast-col-lg-3"><a href="https://www.internsg.com/job/orfeostory-product-intern/">Product Intern</a></div>
          <div class="ast-col-lg-3">Singapore</div>
          <div class="ast-col-lg-3">Internship</div>
        </div>
        """

        jobs = server.parse_internsg_jobs_from_html(html, "product intern", 5)

        self.assertEqual(jobs[0]["company"], "Orfeostory Pte Ltd")

    def test_parse_indeed_fixture(self):
        jobs = server.parse_indeed_jobs_from_html(self.fixture("indeed.html"), "ux research intern", 5)
        self.assertEqual(jobs[0]["url"], "https://sg.indeed.com/viewjob?jk=abc123def456")
        self.assertEqual(jobs[0]["company"], "Research Co")

    def test_parse_indeed_prefers_real_rc_job_key(self):
        html = """
        <div class="job_seen_beacon">
          <a data-jk="78ff7ee6054aa274" href="/rc/clk?jk=78ff7ee6054aa274">
            <span title="Engagement and UX Intern">Engagement and UX Intern</span>
          </a>
          <span data-testid="company-name">NLB National Library Board</span>
          <div data-testid="text-location">Hybrid work in Singapore</div>
        </div>
        <a data-jk="789abcdef0123456" href="/viewjob?jk=789abcdef0123456">
          <span title="Engagement and UX Intern">Engagement and UX Intern</span>
        </a>
        """

        jobs = server.parse_indeed_jobs_from_html(html, "ux research intern", 5)

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["url"], "https://sg.indeed.com/viewjob?jk=78ff7ee6054aa274")
        self.assertEqual(jobs[0]["external_job_id"], "78ff7ee6054aa274")

    def test_parse_serpapi_indeed_apply_option(self):
        payload = {
            "jobs_results": [
                {
                    "title": "UX Research Intern",
                    "company_name": "Research Co",
                    "location": "Singapore",
                    "description": "Support usability testing and product research.",
                    "detected_extensions": {"schedule_type": "Internship"},
                    "apply_options": [
                        {"title": "Apply on Indeed", "link": "https://sg.indeed.com/viewjob?jk=serp123"},
                        {"title": "Apply on Company Site", "link": "https://example.com/jobs/serp123"},
                    ],
                }
            ]
        }

        jobs = server.parse_serpapi_indeed_jobs(payload, "ux research intern", 5, "SG")

        self.assertEqual(jobs[0]["source"], "Indeed")
        self.assertEqual(jobs[0]["url"], "https://sg.indeed.com/viewjob?jk=serp123")
        self.assertEqual(jobs[0]["company"], "Research Co")

    def test_parse_jobstreet_fixture(self):
        jobs = server.parse_jobstreet_jobs_from_html(self.fixture("jobstreet.html"), "ui ux intern", 5)
        self.assertEqual(jobs[0]["source"], "JobStreet")
        self.assertEqual(jobs[0]["url"], "https://sg.jobstreet.com/job/98765432")
        self.assertIn("UI/UX", jobs[0]["position"])

    def test_parse_jobstreet_api_payload(self):
        payload = {
            "data": [
                {
                    "id": "92606186",
                    "title": "AI Intern",
                    "companyName": "Skite Social",
                    "locations": [{"label": "Central Region"}],
                    "workTypes": ["Full time"],
                    "salaryLabel": "SGD 1,200 - 1,800 per month",
                    "teaser": "Hands-on exposure to AI in real business operations.",
                    "classifications": [
                        {
                            "classification": {"description": "Information & Communication Technology"},
                            "subclassification": {"description": "Engineering - Software"},
                        }
                    ],
                }
            ]
        }

        jobs = server.parse_jobstreet_api_jobs(payload, "ai internship", 5)

        self.assertEqual(jobs[0]["source"], "JobStreet")
        self.assertEqual(jobs[0]["url"], "https://sg.jobstreet.com/job/92606186")
        self.assertEqual(jobs[0]["company"], "Skite Social")
        self.assertIn("SGD 1,200", jobs[0]["jd_text"])

    def test_jobstreet_api_parser_drops_missing_or_placeholder_companies(self):
        payload = {
            "data": [
                {"id": "1", "title": "Product Intern", "companyName": ""},
                {"id": "2", "title": "Business Development Associate", "companyName": "Business Development Associate"},
                {"id": "3", "title": "AI Product Intern", "companyName": "Real Startup"},
            ]
        }

        jobs = server.parse_jobstreet_api_jobs(payload, "startup intern", 10)

        self.assertEqual([job["company"] for job in jobs], ["Real Startup"])

    def test_startup_opportunity_source_uses_stable_public_results_and_keeps_entry_roles(self):
        public_jobs = [
            {"company": "SGInnovate", "position": "Intern, Startup Innovation", "source": "JobStreet", "url": "https://sg.jobstreet.com/job/1", "job_type": "Internship", "jd_text": "Singapore startup internship."},
            {"company": "Scale AI Co", "position": "Senior Sales Director", "source": "JobStreet", "url": "https://sg.jobstreet.com/job/2", "job_type": "Full time", "jd_text": "Singapore senior sales role."},
            {"company": "Architecture Group", "position": "Architecture Intern", "source": "JobStreet", "url": "https://sg.jobstreet.com/job/3", "job_type": "Internship", "jd_text": "Returned by a startup search but unrelated."},
        ]
        with mock.patch.object(server, "fetch_jobstreet_jobs", return_value=(public_jobs, [])) as fetch:
            jobs, failures = server.fetch_sg_startup_channel_jobs(10, "SG")

        self.assertEqual(failures, [])
        self.assertEqual([job["company"] for job in jobs], ["SGInnovate"])
        self.assertEqual(jobs[0]["source"], "JobStreet · 创业/AI")
        self.assertFalse(fetch.call_args.kwargs["use_html_fallback"])

    def test_ai_startup_ats_source_keeps_entry_roles_and_spreads_companies(self):
        def ats_fixture(url, company, _focus, _region, _city, _limit):
            if company == "Simular":
                return [], ["Simular ATS limited"]
            return [
                {
                    "company": company,
                    "position": f"{company} Product Intern",
                    "source": "Company Site / ATS",
                    "url": f"{url}/intern",
                    "location": "Singapore",
                    "job_type": "Internship",
                    "jd_text": "Singapore product internship with AI and user research.",
                },
                {
                    "company": company,
                    "position": "Senior AI Engineer",
                    "source": "Company Site / ATS",
                    "url": f"{url}/senior",
                    "location": "Singapore",
                    "job_type": "Full-time",
                    "jd_text": "Singapore senior engineering role requiring eight years of experience.",
                },
                {
                    "company": company,
                    "position": "Product Operations Intern",
                    "source": "Company Site / ATS",
                    "url": f"{url}/us-intern",
                    "location": "Palo Alto",
                    "job_type": "Internship",
                    "jd_text": "Product operations internship in Palo Alto.",
                },
            ], []

        with mock.patch.object(server, "fetch_company_ats_jobs", side_effect=ats_fixture):
            jobs, failures = server.fetch_sg_ai_startup_ats_jobs(3, "SG")

        self.assertEqual(len(jobs), 3)
        self.assertEqual(len({job["company"] for job in jobs}), 3)
        self.assertTrue(all(job["employment_type"] == "Internship" for job in jobs))
        self.assertTrue(all(job["source"] == "ATS · 科技初创" for job in jobs))
        self.assertTrue(any("Simular ATS limited" in failure for failure in failures))

    def test_ai_startup_ats_source_is_registered_as_primary(self):
        self.assertIn("新加坡科技与 AI ATS", server.expected_scan_sources("SG"))
        self.assertEqual(server.scan_source_mode("新加坡科技与 AI ATS"), "primary")
        self.assertEqual(server.SOURCE_LIMITS["AI Startup ATS"], 60)

    def test_sg_tech_ats_includes_verified_product_and_startup_boards(self):
        boards = {company: url for company, url, _focus in server.SG_AI_STARTUP_ATS_BOARDS}

        self.assertEqual(boards["Workato"], "https://job-boards.greenhouse.io/workato")
        self.assertEqual(boards["k-ID"], "https://jobs.ashbyhq.com/k-ID")
        self.assertEqual(boards["Motion Ventures"], "https://job-boards.greenhouse.io/motionventures")
        self.assertEqual(boards["ShopBack"], "https://jobs.lever.co/shopback-2")
        self.assertEqual(boards["Carousell Group"], "https://careers.smartrecruiters.com/carousellgroup")
        self.assertEqual(boards["YouTrip"], "https://apply.workable.com/youtrip")
        self.assertEqual(boards["StraitsX"], "https://job-boards.greenhouse.io/straitsx")
        self.assertEqual(boards["MoneySmart"], "https://job-boards.greenhouse.io/moneysmart")
        self.assertEqual(boards["Razer"], "https://razer.wd3.myworkdayjobs.com/Careers")
        self.assertEqual(boards["Circles"], "https://circles.wd103.myworkdayjobs.com/en-US/Circles")
        self.assertEqual(boards["Wise"], "https://careers.smartrecruiters.com/Wise")
        self.assertEqual(boards["Bosch Singapore"], "https://careers.smartrecruiters.com/BoschGroup")
        self.assertEqual(boards["We. Singapore"], "https://job-boards.greenhouse.io/wesingapore")
        self.assertEqual(boards["Carta"], "https://job-boards.greenhouse.io/carta")
        self.assertEqual(boards["Marshall Wace"], "https://job-boards.greenhouse.io/mwinternshipprogram")

    def test_sg_tech_ats_scans_beyond_first_eight_roles_before_filtering(self):
        requested_limits = []

        def ats_fixture(url, company, focus, region, city, limit):
            requested_limits.append(limit)
            jobs = [
                {
                    "company": company,
                    "position": f"Senior Platform Engineer {index}",
                    "source": "Company Site / ATS",
                    "url": f"{url}/senior-{index}",
                    "location": "Singapore",
                    "job_type": "Full-time",
                    "jd_text": "Senior full-time engineering role.",
                }
                for index in range(12)
            ]
            jobs.append(
                {
                    "company": company,
                    "position": "Product Research Intern",
                    "source": "Company Site / ATS",
                    "url": f"{url}/product-research-intern",
                    "location": "Singapore",
                    "job_type": "Internship",
                    "jd_text": "Singapore product research internship.",
                }
            )
            jobs.append(
                {
                    "company": company,
                    "position": "Frontend Engineer",
                    "source": "Company Site / ATS",
                    "url": f"{url}/frontend-engineer",
                    "location": "Singapore",
                    "job_type": "Company career page",
                    "jd_text": "Build production web experiences. Recent graduate or 1-3 years of experience.",
                }
            )
            return jobs[:limit], []

        with mock.patch.object(server, "SG_AI_STARTUP_ATS_BOARDS", [("Deep Board", "https://jobs.ashbyhq.com/deep", "Product")]):
            with mock.patch.object(server, "fetch_company_ats_jobs", side_effect=ats_fixture):
                jobs, failures = server.fetch_sg_ai_startup_ats_jobs(4, "SG")

        self.assertFalse(failures)
        self.assertGreaterEqual(requested_limits[0], 40)
        self.assertEqual([job["position"] for job in jobs], ["Product Research Intern"])

    def test_cultjobs_parsers_keep_current_singapore_internships(self):
        listing = """
        <article class="job_listing_type-internship job_listing_location-singapore"><h2 class="job-title"><a href="https://cultjobs.com/job/product-uiux-intern/">Product UIUX Intern</a></h2></article>
        <article class="job_listing_type-full-time job_listing_location-singapore"><h2 class="job-title"><a href="https://cultjobs.com/job/designer/">Designer</a></h2></article>
        <article class="job_listing_type-internship job_listing_location-others"><h2 class="job-title"><a href="https://cultjobs.com/job/remote-intern/">Remote Intern</a></h2></article>
        """
        detail = """
        <h1 class="job-detail-title">Product UIUX Intern</h1>
        <div class="job-metas-detail"><a href="https://cultjobs.com/employer/techzu/">Techzu</a><div class="job-location">Singapore</div><div class="job-salary">$800 - $1000 / month</div></div>
        <div class="job-metas-detail-bottom"><a class="type-job">Internship</a></div>
        <div class="job-detail-description">Design product flows, run usability tests, and support AI products. Potential opportunity for full-time conversion.</div>
        <div class="job-detail-detail"><li><div class="text">Expiration date</div><div class="value">August 12, 2099</div></li></div>
        """

        urls = server.parse_cultjobs_listing_urls(listing, 10)
        job = server.parse_cultjobs_detail(detail, urls[0])

        self.assertEqual(urls, ["https://cultjobs.com/job/product-uiux-intern/"])
        self.assertEqual(job["company"], "Techzu")
        self.assertEqual(job["source"], "Cultjobs")
        self.assertIn("full-time conversion", job["jd_text"])
        self.assertEqual(job["salary_min"], 800)
        self.assertEqual(job["salary_max"], 1000)
        self.assertEqual(job["salary_text"], "$800 - $1000 / month")

    def test_cultjobs_detail_drops_expired_jobs(self):
        detail = """
        <h1 class="job-detail-title">Expired UX Intern</h1>
        <div class="job-metas-detail"><a href="https://cultjobs.com/employer/old-co/">Old Co</a><div class="job-location">Singapore</div></div>
        <div class="job-detail-description">UX internship.</div>
        <div class="job-detail-detail"><li><div class="text">Expiration date</div><div class="value">January 1, 2020</div></li></div>
        """
        self.assertIsNone(server.parse_cultjobs_detail(detail, "https://cultjobs.com/job/expired/"))

    def test_cultjobs_detail_drops_non_role_titles(self):
        detail = """
        <h1 class="job-detail-title">Music Games Develop Musical Perception Skills</h1>
        <div class="job-metas-detail"><a href="https://cultjobs.com/employer/course-co/">Course Co</a><div class="job-location">Singapore</div></div>
        <div class="job-metas-detail-bottom"><a class="type-job">Internship</a></div>
        <div class="job-detail-description">An educational programme description.</div>
        """
        self.assertIsNone(server.parse_cultjobs_detail(detail, "https://cultjobs.com/job/music-games/"))

    def test_company_career_link_extraction_rejects_css_assets_and_cleans_escaped_urls(self):
        html = """
        <style>background:url(https://example.com/frontier-career.jpg);background-size:cover</style>
        <link href="https://example.com/wp-json/oembed/1.0/embed?url=https%3A%2F%2Fexample.com%2Fcareers%2F">
        <script>const careers = "https:\\/\\/careers.smartrecruiters.com\\/company\\/openings\\\\";</script>
        <a href="https://careers.smartrecruiters.com/company/openings">View openings</a>
        """

        links = server.extract_embedded_ats_links(html, "https://example.com/careers/")

        self.assertNotIn("https://example.com/frontier-career.jpg", links)
        self.assertFalse(any("/wp-json/" in link for link in links))
        self.assertIn("https://careers.smartrecruiters.com/company/openings", links)
        self.assertFalse(any("\\" in link for link in links))

    def test_jobstreet_distributes_results_across_queries(self):
        def fake_parse(_payload, query, _limit):
            return [
                {
                    "company": f"{query} Company {index}",
                    "position": "Product Intern",
                    "source": "JobStreet",
                    "url": f"https://sg.jobstreet.com/job/{query}-{index}",
                    "location": "Singapore",
                    "jd_text": "Singapore product internship.",
                }
                for index in range(10)
            ]

        with mock.patch.object(server, "http_get", return_value="{}"):
            with mock.patch.object(server, "parse_jobstreet_api_jobs", side_effect=fake_parse):
                with mock.patch.object(server, "jobstreet_search_urls", return_value=[]):
                    jobs, failures = server.fetch_jobstreet_jobs(6, ["MUJI", "POP MART"], "SG")

        self.assertEqual(failures, [])
        self.assertEqual(sum(job["company"].startswith("MUJI") for job in jobs), 3)
        self.assertEqual(sum(job["company"].startswith("POP MART") for job in jobs), 3)

    def test_watched_company_public_source_filters_unrelated_results(self):
        companies = [
            {"company": "MUJI Singapore", "aliases": ["MUJI"]},
            {"company": "POP MART Singapore", "aliases": ["POP MART"]},
        ]
        jobs = [
            {"company": "Muji", "position": "Retail Assistant", "source": "JobStreet", "url": "https://sg.jobstreet.com/job/1"},
            {"company": "Pop Mart (Singapore) Holding Pte Ltd", "position": "Sales Associate", "source": "JobStreet", "url": "https://sg.jobstreet.com/job/2"},
            {"company": "Other Retailer", "position": "Retail Assistant", "source": "JobStreet", "url": "https://sg.jobstreet.com/job/3"},
        ]
        with mock.patch.object(server, "watched_company_scan_items", return_value=companies):
            with mock.patch.object(server, "fetch_jobstreet_jobs", return_value=(jobs, [])):
                matched, failures = server.fetch_watched_company_public_jobs(10, "SG")

        self.assertEqual(failures, [])
        self.assertEqual([job["company"] for job in matched], ["Muji", "Pop Mart (Singapore) Holding Pte Ltd"])

    def test_watched_company_public_source_round_robins_companies(self):
        companies = [
            {"company": "Large Co", "aliases": ["Large Co"]},
            {"company": "Small Co", "aliases": ["Small Co"]},
        ]
        jobs = [
            {"company": "Large Co", "position": f"Role {index}", "source": "JobStreet", "url": f"https://example.com/large-{index}"}
            for index in range(5)
        ] + [
            {"company": "Small Co", "position": "Only Role", "source": "JobStreet", "url": "https://example.com/small"}
        ]
        with mock.patch.object(server, "watched_company_scan_items", return_value=companies):
            with mock.patch.object(server, "fetch_jobstreet_jobs", return_value=(jobs, [])):
                matched, _failures = server.fetch_watched_company_public_jobs(3, "SG")

        self.assertEqual([job["company"] for job in matched], ["Large Co", "Small Co", "Large Co"])

    def test_public_job_link_classifier_rejects_navigation_and_wrong_location(self):
        self.assertEqual(
            server.classify_public_job_link(
                "https://glints.com/sg/opportunities/jobs/product-design-intern/abc123",
                "Product Design Intern",
                "Acme Studio Product Design Intern Singapore",
                "SG",
            ),
            "Glints",
        )
        self.assertEqual(
            server.classify_public_job_link(
                "https://www.nodeflair.com/jobs/acme-product-designer-123456",
                "Product Designer",
                "Acme Product Designer Singapore",
                "SG",
            ),
            "NodeFlair",
        )
        self.assertEqual(
            server.classify_public_job_link(
                "https://wellfound.com/jobs/4417538-product-designer",
                "Product Designer",
                "Acme AI Product Designer Singapore",
                "SG",
            ),
            "Wellfound",
        )
        self.assertIsNone(
            server.classify_public_job_link(
                "https://wellfound.com/role/l/product-manager/united-states",
                "View all product jobs",
                "Product jobs in the United States",
                "SG",
            )
        )
        self.assertIsNone(
            server.classify_public_job_link(
                "https://wellfound.com/jobs/4417538-product-designer",
                "Product Designer",
                "Acme AI Product Designer United States",
                "SG",
            )
        )

    def test_public_search_parser_keeps_real_job_cards_and_company(self):
        html = """
        <main>
          <a href="https://wellfound.com/role/l/designer/united-states">View all design jobs</a>
          <article>
            <a href="https://wellfound.com/jobs/4417538-product-designer">Product Designer</a>
            <span data-company-name>Acme AI</span>
            <span>Singapore</span>
          </article>
          <article>
            <a href="https://wellfound.com/jobs/4363739-senior-product-designer">Senior Product Designer</a>
            <span data-company-name>US Design Co</span>
            <span>United States</span>
          </article>
        </main>
        """

        jobs = server.parse_public_search_jobs_from_html(
            html,
            "https://wellfound.com/jobs?keywords=product&locations=Singapore",
            "Glints / NodeFlair / Startups",
            "SG",
            "Singapore",
            10,
        )

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["company"], "Acme AI")
        self.assertEqual(jobs[0]["source"], "Wellfound")
        self.assertEqual(jobs[0]["position"], "Product Designer")

    def test_careers_gov_algolia_parser_keeps_official_internships(self):
        payload = {
            "hits": [
                {
                    "objectID": "HRP:17828658/005056a3-d347-1fe1-9fe7-48a69483a2ad",
                    "jobSource": "HRP",
                    "title": "Intern (Digital Capabilities), Registries Operations & Systems",
                    "description": "Evaluate AI opportunities and improve the user experience of public systems.",
                    "employmentType": "Internship",
                    "agency": "Intellectual Property Office of Singapore",
                    "department": "InfoComm, Technology, New Media Communications",
                    "activityTimestamp": 1783987200000,
                },
                {
                    "objectID": "HRP:123/ignored",
                    "jobSource": "HRP",
                    "title": "Senior Finance Director",
                    "description": "Lead finance.",
                    "employmentType": "Permanent",
                    "agency": "Example Agency",
                },
            ]
        }

        jobs = server.parse_careers_gov_algolia_jobs(payload, "product intern", 10)

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["source"], "Careers@Gov")
        self.assertEqual(jobs[0]["company"], "Intellectual Property Office of Singapore")
        self.assertEqual(jobs[0]["employment_type"], "Internship")
        self.assertEqual(
            jobs[0]["url"],
            "https://jobs.careers.gov.sg/jobs/hrp/17828658/005056a3-d347-1fe1-9fe7-48a69483a2ad",
        )

    def test_careers_gov_detail_parser_keeps_requirements_and_closing_date(self):
        html = """
        <html><body>
          <nav>A Singapore Government Agency Website Search Save</nav>
          <h1>Product Experience Intern</h1>
          <div><span>Internship</span><span>Closing on 30 Aug 2026</span></div>
          <section><h2>What the role is</h2><p>Improve a public-facing digital service.</p></section>
          <section><h2>What you will be working on</h2><p>Run user research and create Figma prototypes.</p></section>
          <section><h2>What we are looking for</h2><p>Open to students. Singapore Citizen only.</p></section>
          <section><h2>About your application process</h2><p>This job is closing on 30 Aug 2026.</p></section>
          <footer>Browse all jobs Privacy</footer>
        </body></html>
        """
        listing = {
            "company": "Example Agency",
            "position": "Product Experience Intern",
            "source": "Careers@Gov",
            "url": "https://jobs.careers.gov.sg/jobs/hrp/123/example",
            "jd_text": "Short summary.",
        }

        parsed = server.parse_careers_gov_detail_html(html, listing)

        self.assertIn("Run user research", parsed["jd_text"])
        self.assertIn("Singapore Citizen only", parsed["jd_text"])
        self.assertIn("Closing date: 30 Aug 2026", parsed["jd_text"])
        self.assertNotIn("Browse all jobs", parsed["jd_text"])
        _score, flags, _notes = server.score_job("Example Agency", parsed["position"], parsed["jd_text"], parsed["source"])
        self.assertIn("citizen_or_pr_only", flags)

    def test_careers_gov_fetch_round_robins_queries_and_enriches_details(self):
        def search_fixture(query, _limit):
            suffix = query.replace(" ", "-")
            return [
                {
                    "company": f"{query} Agency",
                    "position": f"{query.title()} Role",
                    "source": "Careers@Gov",
                    "url": f"https://jobs.careers.gov.sg/jobs/hrp/{suffix}/uuid",
                    "external_job_id": f"{suffix}/uuid",
                    "location": "Singapore",
                    "region": "SG",
                    "city": "Singapore",
                    "source_region": "SG",
                    "job_type": "Internship",
                    "employment_type": "Internship",
                    "jd_text": f"{query} public service internship.",
                }
            ]

        with mock.patch.object(server, "search_careers_gov_jobs", side_effect=search_fixture):
            with mock.patch.object(
                server,
                "http_get",
                return_value="<h1>Intern</h1><section><h2>What the role is</h2><p>Full detail.</p></section>",
            ):
                jobs, failures = server.fetch_careers_gov_jobs(4, "SG")

        self.assertFalse(failures)
        self.assertEqual(len(jobs), 4)
        self.assertEqual(len({job["company"] for job in jobs}), 4)
        self.assertTrue(all("Full detail" in job["jd_text"] for job in jobs))

    def test_internsg_detail_parser_excludes_site_navigation(self):
        html = """
        <nav>Main Menu Community Marketing Articles</nav>
        <div class="isg-detail-container ast-row no-gutters">
          <div class="ast-row detail-even">
            <div class="ast-col-md-2 font-weight-bold">Job Description</div>
            <div class="ast-col-md-10">Support supply chain systems and write software tooling.</div>
          </div>
        </div>
        <footer>Advertise with InternSG</footer>
        """

        detail = server.parse_internsg_detail_text(html)

        self.assertIn("Support supply chain systems", detail)
        self.assertNotIn("Main Menu", detail)
        self.assertNotIn("Community Marketing", detail)

    def test_job_matching_text_removes_source_boilerplate(self):
        internsg = server.job_matching_text(
            {
                "company": "Aerospace Co",
                "position": "Parts Support Intern",
                "source": "InternSG",
                "jd_text": "Main Menu Marketing Community About Us Job Description Technical parts and SAP support. Share this page Related Posts Healthcare marketing roles.",
            }
        )
        linkedin = server.job_matching_text(
            {
                "company": "Luxury Co",
                "position": "Supply Chain Intern",
                "source": "LinkedIn",
                "jd_text": "Use AI to assess how you fit Get AI-powered advice. Sign in. Position Manage inventory and logistics.",
            }
        )

        self.assertNotIn("marketing community", internsg.lower())
        self.assertIn("technical parts", internsg.lower())
        self.assertNotIn("healthcare marketing", internsg.lower())
        self.assertNotIn("ai-powered advice", linkedin.lower())
        self.assertIn("manage inventory", linkedin.lower())

    def test_public_search_circuit_breaks_per_host_without_blocking_other_hosts(self):
        calls = []

        def fake_http_get(url, **_kwargs):
            calls.append(url)
            if "glints.com" in url or "nodeflair.com" in url:
                raise RuntimeError("HTTP Error 403: Forbidden")
            return "<main></main>"

        with mock.patch.object(server, "region_queries", return_value=["one", "two", "three", "four"]):
            with mock.patch.object(server, "http_get", side_effect=fake_http_get):
                jobs, failures = server.generic_public_search_jobs(
                    "Glints / NodeFlair / Startups",
                    [
                        "https://glints.com/sg/opportunities/jobs/explore?keyword={query}",
                        "https://www.nodeflair.com/sg/jobs?query={query}",
                        "https://wellfound.com/jobs?keywords={query}&locations=Singapore",
                    ],
                    10,
                    "SG",
                )

        self.assertEqual(jobs, [])
        self.assertEqual(sum("glints.com" in url for url in calls), 2)
        self.assertEqual(sum("nodeflair.com" in url for url in calls), 2)
        self.assertEqual(sum("wellfound.com" in url for url in calls), 4)
        self.assertEqual(len(failures), 4)

    def test_public_search_marks_a_functionally_unavailable_page_as_limited(self):
        unavailable_html = "<main>We're temporarily unable to search for jobs. Please try again later.</main>"
        with mock.patch.object(server, "region_queries", return_value=["one", "two", "three"]):
            with mock.patch.object(server, "http_get", return_value=unavailable_html) as get:
                jobs, failures = server.generic_public_search_jobs(
                    "MyCareersFuture",
                    ["https://www.mycareersfuture.gov.sg/search?search={query}"],
                    10,
                    "SG",
                )

        self.assertEqual(jobs, [])
        self.assertEqual(get.call_count, 2)
        self.assertEqual(len(failures), 2)
        self.assertTrue(server.has_limited_failure(failures))

    def test_mycareersfuture_api_parser_keeps_open_local_internships(self):
        payload = {
            "results": [
                {
                    "uuid": "sg-intern-1",
                    "title": "Product Design Intern",
                    "description": "<p>Design product flows and run user research.</p>",
                    "status": {"id": "102", "jobStatus": "Open"},
                    "minimumYearsExperience": 0,
                    "employmentTypes": [{"employmentType": "Internship/Attachment"}],
                    "positionLevels": [{"position": "Fresh/entry level"}],
                    "postedCompany": {"name": "EXAMPLE PTE. LTD."},
                    "address": {"isOverseas": False, "districts": [{"location": "D01 Marina"}]},
                    "salary": {"minimum": 1200, "maximum": 1800, "type": {"salaryType": "Monthly"}},
                    "skills": [{"skill": "Figma"}, {"skill": "User Research"}],
                    "metadata": {
                        "newPostingDate": "2099-07-14",
                        "expiryDate": "2099-08-13",
                        "jobDetailsUrl": "https://www.mycareersfuture.gov.sg/job/design/product-design-intern-sg-intern-1",
                    },
                },
                {
                    "uuid": "overseas-1",
                    "title": "Marketing Intern",
                    "description": "Overseas internship.",
                    "status": "Open",
                    "employmentTypes": [{"employmentType": "Internship/Attachment"}],
                    "postedCompany": {"name": "OVERSEAS CO"},
                    "address": {"isOverseas": True, "overseasCountry": "Australia"},
                    "metadata": {"expiryDate": "2099-08-13"},
                },
            ]
        }

        jobs = server.parse_mycareersfuture_api_jobs(payload, 10)

        self.assertEqual([job["position"] for job in jobs], ["Product Design Intern"])
        self.assertEqual(jobs[0]["company"], "EXAMPLE PTE. LTD.")
        self.assertEqual(jobs[0]["source"], "MyCareersFuture")
        self.assertEqual(jobs[0]["location"], "Singapore · D01 Marina")
        self.assertIn("SGD 1200 - 1800 Monthly", jobs[0]["jd_text"])
        self.assertIn("Figma", jobs[0]["jd_text"])

    def test_mycareersfuture_fetch_uses_public_api_and_deduplicates_queries(self):
        payload = {
            "results": [
                {
                    "uuid": "mcf-1",
                    "title": "AI Product Intern",
                    "description": "Build AI product experiments in Singapore.",
                    "status": "Open",
                    "employmentTypes": [{"employmentType": "Internship/Attachment"}],
                    "postedCompany": {"name": "PUBLIC API CO"},
                    "address": {"isOverseas": False, "districts": []},
                    "metadata": {
                        "expiryDate": "2099-08-13",
                        "jobDetailsUrl": "https://www.mycareersfuture.gov.sg/job/product/ai-product-intern-mcf-1",
                    },
                }
            ]
        }
        with mock.patch.object(server, "http_post_json", return_value=payload) as post:
            jobs, failures = server.fetch_mycareersfuture_jobs(10, "SG")

        self.assertFalse(failures)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["source"], "MyCareersFuture")
        self.assertGreater(post.call_count, 1)
        self.assertTrue(all("/v2/search?" in call.args[0] for call in post.call_args_list))

    def test_internship_sg_search_parser_keeps_early_career_roles_and_rejects_noise(self):
        html = """
        <a class="panel" href="/internships/product-design-intern-example-1">
          <span class="lbl">EXAMPLE DESIGN PTE. LTD.</span>
          <h3>Product Design Intern</h3>
          <div class="mono"><span>Singapore</span><span>·</span><span>Design</span><span>·</span><span>Hybrid</span><span>·</span><span>SGD 1,200/mo</span></div>
        </a>
        <a class="panel" href="/internships/senior-product-manager-example-2">
          <span class="lbl">SENIOR CO</span>
          <h3>Senior Product Manager</h3>
          <div class="mono"><span>Singapore</span><span>·</span><span>Product</span></div>
        </a>
        <a class="panel" href="/internships/ai-product-trainee-example-3">
          <span class="lbl">AI STARTUP SG</span>
          <h3>AI Product Trainee</h3>
          <div class="mono"><span>ONE-NORTH</span><span>·</span><span>Product</span><span>·</span><span>On-site</span></div>
        </a>
        """

        jobs = server.parse_internship_sg_search_html(html, "product design", 10)

        self.assertEqual([job["position"] for job in jobs], ["Product Design Intern", "AI Product Trainee"])
        self.assertEqual(jobs[0]["company"], "EXAMPLE DESIGN PTE. LTD.")
        self.assertEqual(jobs[0]["source"], "Internship.sg")
        self.assertEqual(jobs[0]["location"], "Singapore")
        self.assertIn("SGD 1,200/mo", jobs[0]["jd_text"])

    def test_internship_sg_detail_parser_enriches_job_and_keeps_original_link_as_evidence(self):
        html = """
        <h1>Product Design Intern</h1>
        <a href="/companies/example-design">EXAMPLE DESIGN PTE. LTD.</a>
        <dl>
          <div><dt>Location</dt><dd>ONE-NORTH</dd><dd>Hybrid</dd></div>
          <div><dt>Allowance</dt><dd>SGD 1,200/mo</dd></div>
          <div><dt>Duration</dt><dd>6 months</dd></div>
        </dl>
        <div class="prose-editorial"><p class="whitespace-pre-line">Work with product managers, conduct user research and build Figma prototypes. Strong interns may convert to a full-time role.</p></div>
        <a href="https://www.mycareersfuture.gov.sg/job/design/product-design-intern-example">the original listing</a>
        """
        listing = {
            "company": "EXAMPLE DESIGN PTE. LTD.",
            "position": "Product Design Intern",
            "source": "Internship.sg",
            "url": "https://internship.sg/internships/product-design-intern-example-1",
            "jd_text": "Listing summary.",
        }

        job = server.parse_internship_sg_detail_html(html, listing)

        self.assertEqual(job["location"], "ONE-NORTH · Hybrid")
        self.assertEqual(job["salary_text"], "SGD 1,200/mo")
        self.assertEqual(job["job_type"], "Internship · 6 months")
        self.assertIn("conduct user research", job["jd_text"])
        self.assertIn("Original listing: https://www.mycareersfuture.gov.sg/", job["jd_text"])

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
        self.assertEqual(server.detect_employment_type("Product & AI Engagement Trainee"), "Graduate")
        self.assertEqual(server.detect_employment_type("Full-time UX Designer"), "Full-time")
        self.assertEqual(server.detect_employment_type("Contract UX Researcher"), "Contract")
        self.assertEqual(
            server.detect_employment_type(
                "Python Developer",
                "Seniority level Mid-Senior level Employment type Contract Job function Information Technology",
                "Internship / Full-time",
            ),
            "Contract",
        )

    def test_salary_parser_rejects_benefits_funding_and_business_metrics(self):
        false_salary_texts = [
            "We provide a monthly fund of $100 to spend on activities that bring you joy.",
            "The company has raised over SGD 95 million from renowned investors.",
            "ShopBack powers over US$5.5 billion in annual sales.",
            "The firm manages over US$7 billion in assets.",
            "Our clients are enterprise, paying $60-144K per year.",
        ]

        for text in false_salary_texts:
            with self.subTest(text=text):
                self.assertIsNone(server.parse_salary_info("Product Intern", text, "Internship", "SG")["salary_min"])

    def test_salary_parser_handles_compact_ranges_and_skips_earlier_metrics(self):
        annual = server.parse_salary_info(
            "Project Management Intern",
            "The company raised $20 million. Compensation is $60-144K per year.",
            "Internship",
            "SG",
        )
        monthly = server.parse_salary_info(
            "Software Engineering Intern",
            "Base pay range SGD 1,000/mo - SGD 1,500/mo.",
            "Internship",
            "SG",
        )

        self.assertEqual((annual["salary_min"], annual["salary_max"], annual["salary_period"]), (60000, 144000, "yearly"))
        self.assertEqual((monthly["salary_min"], monthly["salary_max"], monthly["salary_period"]), (1000, 1500, "monthly"))

    def test_salary_parser_rejects_implausible_source_ranges(self):
        malformed_ranges = [
            "Base pay range SGD 1/mo - SGD 1,500/mo.",
            "Compensation $3.90 - $6.80 a month.",
            "Pay range $600 - $900 per hour.",
        ]

        for text in malformed_ranges:
            with self.subTest(text=text):
                self.assertIsNone(server.parse_salary_info("Product Intern", text, "Internship", "SG")["salary_min"])

    def test_direction_matching_does_not_promote_generic_jd_keywords(self):
        unrelated = {
            "company": "Bifrost AI",
            "position": "Supply Chain Intern",
            "source": "ATS · AI 初创",
            "jd_text": "Improve automation workflows, create a prototype, and prepare content for stakeholders.",
        }
        ai_direction = server.career_direction_by_id("ai-product")
        ux_direction = server.career_direction_by_id("ux-product-design")
        growth_direction = server.career_direction_by_id("growth-content")

        self.assertEqual(server.direction_match_for_job(unrelated, ai_direction)[0], 0)
        self.assertEqual(server.direction_match_for_job(unrelated, ux_direction)[0], 0)
        self.assertEqual(server.direction_match_for_job(unrelated, growth_direction)[0], 0)
        self.assertNotIn("ai_related", server.content_tag_ids_for_job(unrelated))
        self.assertNotIn("ux_related", server.content_tag_ids_for_job(unrelated))

    def test_content_tags_clean_job_text_once(self):
        job = {
            "company": "Example AI",
            "position": "AI Product Intern",
            "source": "ATS · 科技初创",
            "jd_text": "Build AI product prototypes and support user research.",
        }
        with mock.patch.object(server, "job_matching_text", wraps=server.job_matching_text) as matching_text:
            server.content_tag_ids_for_job(job)

        self.assertEqual(matching_text.call_count, 1)

    def test_ranking_reuses_direction_matches_for_job_tags(self):
        job = {
            "company": "Example AI",
            "position": "AI Product Intern",
            "source": "ATS · 科技初创",
            "region": "SG",
            "location": "Singapore",
            "status": "New",
            "score": 4.0,
            "employment_type": "Internship",
            "jd_text": "Build AI product prototypes and support user research.",
        }
        with mock.patch.object(server, "direction_match_for_job", wraps=server.direction_match_for_job) as matcher:
            server.rank_job_with_preferences(
                job,
                ["ai-product", "ux-product-design", "user-research"],
                {},
                "SG",
                set(),
                server.default_region_context("SG"),
            )

        checked_ids = [call.args[1]["id"] for call in matcher.call_args_list]
        self.assertEqual(checked_ids.count("ai-product"), 1)
        self.assertEqual(checked_ids.count("ux-product-design"), 1)
        self.assertEqual(checked_ids.count("user-research"), 1)

    def test_direction_matching_does_not_relabel_finance_or_legal_roles_from_company_boilerplate(self):
        company_boilerplate = (
            "We build AI automation, LLM workflows and UX tools. "
            "Our product team runs user research, usability tests and product design."
        )
        jobs = [
            {"company": "k-ID", "position": "Finance Intern (SG)", "source": "ATS · 科技初创", "jd_text": company_boilerplate},
            {"company": "k-ID", "position": "Legal Internship Program 2026", "source": "ATS · 科技初创", "jd_text": company_boilerplate},
        ]

        for job in jobs:
            with self.subTest(position=job["position"]):
                self.assertEqual(server.direction_match_for_job(job, server.career_direction_by_id("ai-product"))[0], 0)
                self.assertEqual(server.direction_match_for_job(job, server.career_direction_by_id("ux-product-design"))[0], 0)
                self.assertNotIn("ai_related", server.content_tag_ids_for_job(job))
                self.assertNotIn("product_related", server.content_tag_ids_for_job(job))
                self.assertNotIn("ux_related", server.content_tag_ids_for_job(job))

    def test_ranking_softly_downweights_non_target_functions_without_direction_matches(self):
        jobs = [
            {
                "company": "Example Product Company",
                "position": "Finance Intern",
                "source": "Company Site / ATS",
                "region": "SG",
                "location": "Singapore",
                "status": "Recommended",
                "score": 3.5,
                "employment_type": "Internship",
                "jd_text": "Support accounting, tax reporting, and financial controls in Singapore.",
            },
            {
                "company": "Hardware Company",
                "position": "Repair Operations Intern",
                "source": "Company Site / ATS",
                "region": "SG",
                "location": "Singapore",
                "status": "Recommended",
                "score": 4.2,
                "employment_type": "Internship",
                "jd_text": "Oversee repair centre operations, RMA receiving, and maintenance reporting.",
            },
        ]

        for job in jobs:
            with self.subTest(position=job["position"]):
                ranked = server.rank_job_with_preferences(
                    job,
                    ["ai-product", "ux-product-design"],
                    {},
                    "SG",
                    set(),
                    server.default_region_context("SG"),
                )

                self.assertEqual(ranked["direction_mismatch_adjustment"], -0.55)
                self.assertIn("方向偏离", ranked["recommendation_reason"])

    def test_direction_matching_keeps_title_and_specific_jd_signals(self):
        ai_job = {
            "company": "Example Group",
            "position": "GenAI Product Development Intern",
            "source": "LinkedIn",
            "jd_text": "Build internal tools with product teams.",
        }
        ux_job = {
            "company": "Example Group",
            "position": "Digital Project Intern",
            "source": "InternSG",
            "jd_text": "Create UX flows and Figma prototypes for customer journeys.",
        }

        self.assertGreater(server.direction_match_for_job(ai_job, server.career_direction_by_id("ai-product"))[0], 0)
        self.assertGreater(server.direction_match_for_job(ux_job, server.career_direction_by_id("ux-product-design"))[0], 0)
        self.assertIn("ai_related", server.content_tag_ids_for_job(ai_job))
        self.assertIn("ux_related", server.content_tag_ids_for_job(ux_job))

    def test_service_design_requires_method_evidence_beyond_a_healthcare_domain(self):
        healthcare_operations = {
            "company": "Healthcare Staffing Co",
            "position": "Healthcare Business Support Intern | Healthcare Operations Intern",
            "source": "Internship.sg",
            "jd_text": "Support clinic schedules, process invoices, update spreadsheets, and coordinate daily operations.",
        }

        score, hits = server.direction_match_for_job(
            healthcare_operations,
            server.career_direction_by_id("service-design"),
        )

        self.assertEqual(score, 0)
        self.assertEqual(hits, [])
        self.assertNotIn("ux_related", server.content_tag_ids_for_job(healthcare_operations))

    def test_product_profile_downweights_mechanical_and_healthcare_operations_roles(self):
        jobs = [
            {
                "company": "Industrial Engineering Co",
                "position": "Mechanical Design and Process Development Intern",
                "jd_text": "Create CAD drawings, validate mechanical parts, and improve manufacturing processes.",
                "score": 4.2,
            },
            {
                "company": "Healthcare Staffing Co",
                "position": "Healthcare Business Support Intern | Healthcare Operations Intern",
                "jd_text": "Support clinic schedules, invoices, spreadsheets, and daily healthcare operations.",
                "score": 4.0,
            },
        ]

        for job in jobs:
            ranked = server.rank_job_with_preferences(
                {
                    **job,
                    "source": "Company Site / ATS",
                    "region": "SG",
                    "location": "Singapore",
                    "status": "Recommended",
                    "employment_type": "Internship",
                },
                ["ai-product", "ux-product-design", "user-research", "service-design"],
                {},
                "SG",
                set(),
                server.default_region_context("SG"),
            )

            with self.subTest(position=job["position"]):
                self.assertEqual(ranked["matched_directions"], [])
                self.assertEqual(ranked["direction_mismatch_adjustment"], -0.55)
                self.assertIn("方向偏离", ranked["recommendation_reason"])

    def test_ai_product_direction_rejects_pure_technical_and_presales_roles(self):
        ai_product = server.career_direction_by_id("ai-product")
        ux_product = server.career_direction_by_id("ux-product-design")
        unrelated_jobs = [
            {
                "company": "Gaming Co",
                "position": "AI Data Engineer Intern",
                "source": "Company Site / ATS",
                "jd_text": "Build AI data pipelines, automate workflows, and deploy models for product teams.",
            },
            {
                "company": "Storage Co",
                "position": "Data Science Intern",
                "source": "Company Site / ATS",
                "jd_text": "Use machine learning and AI to analyze product telemetry and prototype models.",
            },
            {
                "company": "Payments Co",
                "position": "Pre-Sales Payment & Partner Success Intern",
                "source": "Company Site / ATS",
                "jd_text": "Explain AI workflows and product design choices to prospective partners.",
            },
            {
                "company": "Autonomy Co",
                "position": "Autonomous Vehicle Integration & Validation Intern (Software Tools)",
                "source": "Company Site / ATS",
                "jd_text": "Build physical AI systems, automate validation, and improve tool usability.",
            },
            {
                "company": "Robotics Co",
                "position": "Robot Learning Intern",
                "source": "Company Site / ATS",
                "jd_text": "Develop AI training algorithms, prototype robot interaction, and evaluate models.",
            },
            {
                "company": "Consulting Co",
                "position": "AI/Data Intern",
                "source": "Company Site / ATS",
                "jd_text": "Analyze data with AI and prepare insights for digital transformation projects.",
            },
        ]

        for job in unrelated_jobs:
            with self.subTest(position=job["position"]):
                self.assertEqual(server.direction_match_for_job(job, ai_product)[0], 0)
                self.assertEqual(server.direction_match_for_job(job, ux_product)[0], 0)
                self.assertNotIn("product_related", server.content_tag_ids_for_job(job))

        genuine_product_job = {
            "company": "Applied AI Co",
            "position": "AI Product Engineer Intern",
            "source": "Company Site / ATS",
            "jd_text": "Own user discovery, product requirements, prototypes, and AI feature evaluation.",
        }
        self.assertGreater(server.direction_match_for_job(genuine_product_job, ai_product)[0], 0)
        self.assertIn("product_related", server.content_tag_ids_for_job(genuine_product_job))

    def test_pure_technical_ai_role_gets_product_profile_mismatch_penalty(self):
        job = {
            "company": "Storage Co",
            "position": "AI Data Engineer Intern",
            "source": "Company Site / ATS",
            "region": "SG",
            "location": "Singapore",
            "status": "Recommended",
            "score": 4.6,
            "employment_type": "Internship",
            "jd_text": "Build AI data pipelines, automate workflows, and deploy models for product teams.",
        }

        ranked = server.rank_job_with_preferences(
            job,
            ["ai-product", "ux-product-design", "user-research"],
            {},
            "SG",
            set(),
            server.default_region_context("SG"),
        )

        self.assertEqual(ranked["matched_directions"], [])
        self.assertEqual(ranked["direction_mismatch_adjustment"], -0.55)
        self.assertIn("方向偏离", ranked["recommendation_reason"])

    def test_job_tags_ignore_source_queries_and_internsg_related_jobs(self):
        linkedin_job = {
            "company": "Flo Energy",
            "position": "Product Design Intern",
            "source": "LinkedIn",
            "jd_text": "Design customer experiences in Figma.\nSource query: ai ux intern",
        }
        internsg_job = {
            "company": "Payments Co",
            "position": "Funding and Settlement Intern",
            "source": "InternSG",
            "jd_text": "Job Description\nSupport reconciliation and settlement automation.\nRelated Job Searches: Computing and Machine Learning Intern",
        }

        self.assertNotIn("ai_related", server.content_tag_ids_for_job(linkedin_job))
        self.assertNotIn("ai_related", server.content_tag_ids_for_job(internsg_job))

    def test_direction_matching_ignores_internal_official_board_focus_metadata(self):
        engineering_job = {
            "company": "Example AI",
            "position": "Engineering Internship Program 2026",
            "source": "ATS · 科技初创",
            "jd_text": (
                "Example AI official career match\n"
                "Role: Engineering Internship Program 2026\n"
                "Focus: Product, HCI, UX, engineering and operations internships\n"
                "Source: https://jobs.example.com/example\n"
                "URL: https://jobs.example.com/example/engineering-intern\n\n"
                "Build backend services, write production code, and maintain cloud infrastructure."
            ),
        }

        matching_text = server.job_matching_text(engineering_job)

        self.assertNotIn("official career match", matching_text.lower())
        self.assertNotIn("focus", matching_text.lower())
        self.assertEqual(
            server.direction_match_for_job(engineering_job, server.career_direction_by_id("ux-product-design"))[0],
            0,
        )
        self.assertNotIn("ux_related", server.content_tag_ids_for_job(engineering_job))

    def test_product_tag_requires_product_role_evidence(self):
        ai_compliance_job = {
            "company": "Utilities Group",
            "position": "Group Ethics & Compliance Intern",
            "source": "InternSG",
            "jd_text": "Job Description\nSupport AI-enabled due diligence workflows and test AI pilots.",
        }
        product_marketing_job = {
            "company": "Example Group",
            "position": "Product Marketing Intern",
            "source": "JobStreet",
            "jd_text": "Support launches, campaigns, and customer research.",
        }

        self.assertIn("ai_related", server.content_tag_ids_for_job(ai_compliance_job))
        self.assertNotIn("product_related", server.content_tag_ids_for_job(ai_compliance_job))
        self.assertIn("product_related", server.content_tag_ids_for_job(product_marketing_job))
        self.assertEqual(
            server.detect_employment_type(
                "Principal / Lead Designer, Consulting Practice",
                "What we are looking for: 10+ years in experience design.",
                "Internship / Full-time",
            ),
            "Full-time",
        )

    def test_job_metadata_detects_pathway_conversion_visa_and_language(self):
        metadata = server.job_metadata(
            "AI Product Intern",
            "Return offer track with full-time conversion, Mandarin support for Greater China users, and Employment Pass sponsorship support for strong performers.",
            "Internship",
            "SG",
            "ByteDance",
            "Company Site / ATS",
        )

        self.assertEqual(metadata["conversion_signal"], "strong")
        self.assertEqual(metadata["visa_sponsorship_signal"], "possible")
        self.assertEqual(metadata["language_signal"], "chinese_friendly_possible")
        self.assertGreaterEqual(metadata["pathway_score"], 4.0)
        self.assertTrue(metadata["pathway_evidence_json"])

        blocked = server.job_metadata(
            "UX Intern",
            "Singaporeans / PR only. No visa sponsorship. Short internship with no conversion to full-time.",
            "Internship",
            "SG",
        )
        self.assertEqual(blocked["conversion_signal"], "none")
        self.assertEqual(blocked["visa_sponsorship_signal"], "unlikely")

        right_to_work_only = server.job_metadata(
            "Marketing Associate Intern",
            "Based in Singapore with right to work in Singapore (visa sponsorship not available). Opportunity for full-time conversion based on performance.",
            "Internship",
            "SG",
        )
        self.assertEqual(right_to_work_only["conversion_signal"], "strong")
        self.assertEqual(right_to_work_only["visa_sponsorship_signal"], "unlikely")

        risk_tags = server.job_tag_ids_for_preferences(
            {**right_to_work_only, "position": "Marketing Associate Intern", "source": "Company Site / ATS"},
            "SG",
            {"sponsorship_signal": "possible"},
        )
        self.assertIn("visa_unlikely", risk_tags)
        self.assertNotIn("visa_possible", risk_tags)

    def test_company_jsonld_and_greenhouse_jobs_parse(self):
        html = """
        <script type="application/ld+json">
        {"@type":"JobPosting","title":"AI Product Intern","url":"https://example.com/jobs/ai-product-intern","description":"Internship with product and user research work.","jobLocation":{"address":{"addressLocality":"Singapore"}}}
        </script>
        """
        jobs = server.parse_company_jsonld_jobs(html, "https://example.com/careers", "Example AI", "AI product internships", "SG", "Singapore", 5)
        self.assertEqual(jobs[0]["position"], "AI Product Intern")
        self.assertEqual(jobs[0]["source"], "Company Site / ATS")

        payload = {
            "jobs": [
                {
                    "title": "UX Research Intern",
                    "absolute_url": "https://boards.greenhouse.io/example/jobs/123",
                    "content": "Internship role for UX research and service design.",
                    "location": {"name": "Singapore"},
                },
                {
                    "title": "Growth Intern",
                    "absolute_url": "https://boards.greenhouse.io/example/jobs/456",
                    "content": "Internship role for growth research.",
                    "location": {"name": "Mexico City, Mexico"},
                }
            ]
        }
        with mock.patch.object(server, "http_get", return_value=json.dumps(payload)):
            ats_jobs, failures = server.fetch_company_ats_jobs("https://boards.greenhouse.io/example", "Example AI", "UX research", "SG", "Singapore", 5)

        self.assertFalse(failures)
        self.assertEqual([job["position"] for job in ats_jobs], ["UX Research Intern"])

    def test_smartrecruiters_jobs_use_public_posting_urls_and_employment_metadata(self):
        payload = {
            "content": [
                {
                    "id": "744000135159089",
                    "name": "Luxury Retail Intern",
                    "ref": "https://api.smartrecruiters.com/v1/companies/carousellgroup/postings/744000135159089",
                    "company": {"identifier": "CarousellGroup", "name": "Carousell Group"},
                    "location": {"city": "Singapore", "country": "sg", "fullLocation": "Singapore, , Singapore"},
                    "typeOfEmployment": {"id": "intern", "label": "Intern"},
                    "experienceLevel": {"id": "internship", "label": "Internship"},
                    "department": {"label": "Sales"},
                }
            ]
        }
        with mock.patch.object(server, "http_get", return_value=json.dumps(payload)):
            jobs, failures = server.fetch_company_ats_jobs(
                "https://careers.smartrecruiters.com/carousellgroup",
                "Carousell Group",
                "Marketplace and product internships",
                "SG",
                "Singapore",
                5,
            )

        self.assertFalse(failures)
        self.assertEqual(
            jobs[0]["url"],
            "https://jobs.smartrecruiters.com/CarousellGroup/744000135159089-luxury-retail-intern",
        )
        self.assertIn("Employment: Intern", jobs[0]["jd_text"])
        self.assertIn("Experience: Internship", jobs[0]["jd_text"])
        self.assertEqual(jobs[0]["location"], "Singapore, Singapore")

    def test_smartrecruiters_pages_until_target_region_and_rejects_foreign_jobs(self):
        foreign_page = {
            "offset": 0,
            "limit": 100,
            "totalFound": 101,
            "content": [
                {
                    "id": "foreign-1",
                    "name": "Product Intern",
                    "location": {"fullLocation": "Tallinn, Estonia"},
                }
            ],
        }
        singapore_page = {
            "offset": 100,
            "limit": 100,
            "totalFound": 101,
            "content": [
                {
                    "id": "sg-1",
                    "name": "Analytics Intern",
                    "company": {"identifier": "Wise"},
                    "location": {"fullLocation": "Singapore, Singapore"},
                    "typeOfEmployment": {"label": "Intern"},
                }
            ],
        }

        def smartrecruiters_fixture(url, **_kwargs):
            return json.dumps(singapore_page if "offset=100" in url else foreign_page)

        with mock.patch.object(server, "http_get", side_effect=smartrecruiters_fixture) as fetch:
            jobs, failures = server.fetch_company_ats_jobs(
                "https://careers.smartrecruiters.com/Wise",
                "Wise",
                "Fintech analytics and product internships",
                "SG",
                "Singapore",
                5,
            )

        self.assertFalse(failures)
        self.assertEqual([job["position"] for job in jobs], ["Analytics Intern"])
        listing_urls = [call.args[0] for call in fetch.call_args_list if "/postings?" in call.args[0]]
        self.assertEqual(len(listing_urls), 2)

    def test_smartrecruiters_filters_global_boards_to_the_target_country(self):
        singapore_page = {
            "offset": 0,
            "limit": 100,
            "totalFound": 1,
            "content": [
                {
                    "id": "sg-ai-intern",
                    "name": "Intern, Generative AI Chatbot Development",
                    "company": {"identifier": "BoschGroup"},
                    "location": {"fullLocation": "Singapore, Singapore"},
                    "typeOfEmployment": {"label": "Intern"},
                }
            ],
        }

        with mock.patch.object(server, "http_get", return_value=json.dumps(singapore_page)) as fetch:
            jobs, failures = server.fetch_company_ats_jobs(
                "https://careers.smartrecruiters.com/BoschGroup",
                "Bosch Singapore",
                "AI and product internships",
                "SG",
                "Singapore",
                10,
            )

        self.assertFalse(failures)
        self.assertEqual([job["position"] for job in jobs], ["Intern, Generative AI Chatbot Development"])
        listing_urls = [call.args[0] for call in fetch.call_args_list if "/postings?" in call.args[0]]
        self.assertEqual(len(listing_urls), 1)
        self.assertIn("country=sg", listing_urls[0])

    def test_smartrecruiters_fetches_official_job_ad_sections_for_scoring(self):
        detail_url = "https://api.smartrecruiters.com/v1/companies/BoschGroup/postings/sg-ai-intern"
        listing = {
            "offset": 0,
            "limit": 100,
            "totalFound": 1,
            "content": [
                {
                    "id": "sg-ai-intern",
                    "name": "AI Product Research Intern",
                    "ref": detail_url,
                    "company": {"identifier": "BoschGroup"},
                    "location": {"fullLocation": "Singapore, Singapore"},
                    "typeOfEmployment": {"label": "Intern"},
                }
            ],
        }
        detail = {
            "jobAd": {
                "sections": {
                    "jobDescription": {"text": "Research users and prototype an AI product in Figma."},
                    "qualifications": {"text": "Strong UX research and service design skills."},
                    "additionalInformation": {"text": "High performers may convert to a full-time role."},
                }
            }
        }

        def smartrecruiters_fixture(url, **_kwargs):
            return json.dumps(detail if url == detail_url else listing)

        with mock.patch.object(server, "http_get", side_effect=smartrecruiters_fixture) as fetch:
            jobs, failures = server.fetch_company_ats_jobs(
                "https://careers.smartrecruiters.com/BoschGroup",
                "Bosch Singapore",
                "AI and product internships",
                "SG",
                "Singapore",
                10,
            )

        self.assertFalse(failures)
        self.assertEqual(fetch.call_count, 2)
        self.assertIn("Research users and prototype an AI product in Figma", jobs[0]["jd_text"])
        self.assertIn("High performers may convert to a full-time role", jobs[0]["jd_text"])

    def test_smartrecruiters_does_not_follow_untrusted_detail_refs(self):
        listing = {
            "offset": 0,
            "limit": 100,
            "totalFound": 1,
            "content": [
                {
                    "id": "sg-ai-intern",
                    "name": "AI Product Intern",
                    "ref": "https://attacker.example/private",
                    "location": {"fullLocation": "Singapore, Singapore"},
                }
            ],
        }
        requested_urls = []

        def smartrecruiters_fixture(url, **_kwargs):
            requested_urls.append(url)
            return json.dumps(listing if "/postings?" in url else {})

        with mock.patch.object(server, "http_get", side_effect=smartrecruiters_fixture):
            jobs, failures = server.fetch_company_ats_jobs(
                "https://careers.smartrecruiters.com/BoschGroup",
                "Bosch Singapore",
                "AI and product internships",
                "SG",
                "Singapore",
                10,
            )

        self.assertFalse(failures)
        self.assertEqual(len(jobs), 1)
        self.assertNotIn("https://attacker.example/private", requested_urls)
        self.assertIn(
            "https://api.smartrecruiters.com/v1/companies/BoschGroup/postings/sg-ai-intern",
            requested_urls,
        )

    def test_lever_and_ashby_require_explicit_target_region(self):
        lever_payload = [
            {
                "text": "Product Intern",
                "hostedUrl": "https://jobs.lever.co/example/sg",
                "descriptionPlain": "Product internship.",
                "categories": {"location": "Singapore"},
            },
            {
                "text": "Marketing Intern",
                "hostedUrl": "https://jobs.lever.co/example/us",
                "descriptionPlain": "Marketing internship.",
                "categories": {"location": "New York, United States"},
            },
        ]
        ashby_payload = {
            "jobs": [
                {
                    "title": "AI Product Intern",
                    "jobUrl": "https://jobs.ashbyhq.com/example/sg",
                    "descriptionPlain": "AI product internship.",
                    "locationName": "Singapore",
                },
                {
                    "title": "Research Intern",
                    "jobUrl": "https://jobs.ashbyhq.com/example/mx",
                    "descriptionPlain": "Research internship.",
                    "locationName": "Mexico City, Mexico",
                },
            ]
        }

        with mock.patch.object(server, "http_get", return_value=json.dumps(lever_payload)):
            lever_jobs, _ = server.fetch_company_ats_jobs(
                "https://jobs.lever.co/example", "Example", "Product", "SG", "Singapore", 10
            )
        with mock.patch.object(server, "http_get", return_value=json.dumps(ashby_payload)):
            ashby_jobs, _ = server.fetch_company_ats_jobs(
                "https://jobs.ashbyhq.com/example", "Example", "Product", "SG", "Singapore", 10
            )

        self.assertEqual([job["position"] for job in lever_jobs], ["Product Intern"])
        self.assertEqual([job["position"] for job in ashby_jobs], ["AI Product Intern"])

    def test_workable_company_jobs_parse_and_filter_region(self):
        payload = {
            "jobs": [
                {
                    "title": "AI Product Manager Intern",
                    "url": "https://apply.workable.com/j/abc123",
                    "description": "Support AI product experiments and UX research.",
                    "city": "Singapore",
                    "country": "Singapore",
                    "locations": [{"city": "Singapore", "country": "Singapore", "countryCode": "SG"}],
                },
                {
                    "title": "Finance Manager",
                    "url": "https://apply.workable.com/j/my123",
                    "description": "Finance leadership role.",
                    "city": "Kuala Lumpur",
                    "country": "Malaysia",
                    "locations": [{"city": "Kuala Lumpur", "country": "Malaysia", "countryCode": "MY"}],
                },
            ]
        }
        with mock.patch.object(server, "http_get", return_value=json.dumps(payload)):
            jobs, failures = server.fetch_company_ats_jobs("https://apply.workable.com/youtrip/?lng=en", "YouTrip", "AI product internships", "SG", "Singapore", 5)

        self.assertFalse(failures)
        self.assertEqual([job["position"] for job in jobs], ["AI Product Manager Intern"])
        self.assertEqual(jobs[0]["source"], "Company Site / ATS")

    def test_workday_company_jobs_parse_details_and_filter_region(self):
        listing = {
            "total": 3,
            "jobPostings": [
                {
                    "title": "AI Product Intern",
                    "externalPath": "/job/Singapore/AI-Product-Intern_R-1001",
                    "locationsText": "Singapore",
                    "postedOn": "Posted Today",
                },
                {
                    "title": "Community Intern",
                    "externalPath": "/job/Singapore/Community-Intern_R-1002",
                    "locationsText": "Singapore",
                    "postedOn": "Posted 2 Days Ago",
                },
                {
                    "title": "Marketing Intern",
                    "externalPath": "/job/Shah-Alam/Marketing-Intern_R-1003",
                    "locationsText": "Shah Alam",
                    "postedOn": "Posted Today",
                },
            ],
        }
        details = {
            "R-1001": {
                "jobPostingInfo": {
                    "title": "AI Product Intern",
                    "location": "Singapore",
                    "jobDescription": "<p>Build AI product experiments and research user needs.</p>",
                    "externalUrl": "https://circles.wd103.myworkdayjobs.com/Circles/job/Singapore/AI-Product-Intern_R-1001",
                    "timeType": "Full time",
                    "jobReqId": "R-1001",
                }
            },
            "R-1002": {
                "jobPostingInfo": {
                    "title": "Community Intern",
                    "location": "Singapore",
                    "jobDescription": "<p>Support community growth and content.</p>",
                    "externalUrl": "https://circles.wd103.myworkdayjobs.com/Circles/job/Singapore/Community-Intern_R-1002",
                    "timeType": "Full time",
                    "jobReqId": "R-1002",
                }
            },
        }

        def detail_fixture(url, **_kwargs):
            key = next(key for key in details if key in url)
            return json.dumps(details[key])

        with mock.patch.object(server, "http_post_json", return_value=listing) as post:
            with mock.patch.object(server, "http_get", side_effect=detail_fixture):
                jobs, failures = server.fetch_company_ats_jobs(
                    "https://circles.wd103.myworkdayjobs.com/en-US/Circles",
                    "Circles",
                    "AI product and community internships",
                    "SG",
                    "Singapore",
                    5,
                )

        self.assertFalse(failures)
        self.assertEqual([job["position"] for job in jobs], ["AI Product Intern", "Community Intern"])
        self.assertTrue(all(job["source"] == "Company Site / ATS" for job in jobs))
        self.assertIn("Build AI product experiments", jobs[0]["jd_text"])
        self.assertEqual(jobs[0]["location"], "Singapore")
        self.assertIn("/wday/cxs/circles/Circles/jobs", post.call_args.args[0])


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


class WorkbenchPayloadTests(TempAppMixin, unittest.TestCase):
    def test_actionable_deadline_precedes_higher_scored_job(self):
        deadline = (server.dt.date.today() + server.dt.timedelta(days=3)).strftime(server.DATE_FMT)
        urgent = {
            "id": 1,
            "company": "Urgent Co",
            "position": "Product Intern",
            "source": "ATS",
            "status": "Recommended",
            "application_deadline": deadline,
            "rank_score": 3.4,
            "score": 3.2,
        }
        stronger = {
            "id": 2,
            "company": "Strong Co",
            "position": "Product Intern",
            "source": "ATS",
            "status": "Recommended",
            "application_deadline": "",
            "rank_score": 5.0,
            "score": 5.0,
        }

        payload = server.recommendation_payload_from_ranked_jobs(
            [stronger, urgent], "SG", 2, {}, [], "default", []
        )

        self.assertEqual([job["id"] for job in payload["jobs"]], [1, 2])

    def test_deadline_does_not_override_direction_alignment(self):
        deadline = (server.dt.date.today() + server.dt.timedelta(days=1)).strftime(server.DATE_FMT)
        mismatched = {
            "id": 1,
            "company": "Urgent HR Co",
            "position": "HR Intern",
            "source": "ATS",
            "status": "Recommended",
            "application_deadline": deadline,
            "direction_mismatch_adjustment": -0.55,
            "rank_score": 4.2,
            "score": 3.5,
        }
        aligned = {
            "id": 2,
            "company": "Product Co",
            "position": "Product Intern",
            "source": "ATS",
            "status": "Recommended",
            "direction_mismatch_adjustment": 0,
            "rank_score": 4.0,
            "score": 3.5,
        }

        payload = server.recommendation_payload_from_ranked_jobs(
            [mismatched, aligned], "SG", 2, {}, [], "default", []
        )

        self.assertEqual([job["id"] for job in payload["jobs"]], [2, 1])

    def test_workbench_prioritizes_queued_job_with_near_deadline(self):
        deadline = server.dt.date.today() + server.dt.timedelta(days=2)
        urgent = server.upsert_job(
            {
                "company": "Deadline First Co",
                "position": "Product Intern",
                "source": "Company Site / ATS",
                "url": "https://example.com/deadline-first",
                "jd_text": f"Singapore product internship. Applications close {deadline.strftime('%d %B %Y')}.",
            }
        )
        newer = server.upsert_job(
            {
                "company": "Recently Queued Co",
                "position": "UX Intern",
                "source": "Company Site / ATS",
                "url": "https://example.com/recently-queued",
                "jd_text": "Singapore UX internship with no published closing date.",
            }
        )
        with server.get_db() as conn:
            conn.execute(
                "update jobs set status='Apply Queue', updated_at=? where id=?",
                ((server.dt.datetime.now() - server.dt.timedelta(days=2)).replace(microsecond=0).isoformat(), urgent["id"]),
            )
            conn.execute("update jobs set status='Apply Queue', updated_at=? where id=?", (server.now_iso(), newer["id"]))

        payload = server.workbench_payload({"region": ["SG"]})

        self.assertEqual(payload["queue_preview"][0]["id"], urgent["id"])
        self.assertEqual(payload["queue_preview"][0]["application_deadline"], deadline.strftime(server.DATE_FMT))
        self.assertEqual(payload["queue_preview"][0]["deadline_status"], "urgent")
        self.assertEqual(payload["queue_preview"][0]["queue_priority"], "today")
        self.assertEqual(payload["queue_preview"][0]["queue_priority_label"], "今天优先")
        self.assertIn("优先投递", payload["queue_preview"][0]["next_step"])

    def test_supplemental_recommendations_put_direction_mismatches_after_aligned_jobs(self):
        current_date = server.today()
        older_date = (server.dt.date.today() - server.dt.timedelta(days=3)).strftime(server.DATE_FMT)
        mismatched = {
            "id": 1,
            "company": "Fresh Finance Co",
            "position": "Finance Intern",
            "source": "ATS",
            "status": "Recommended",
            "batch_date": current_date,
            "score": 4.9,
            "rank_score": 4.9,
            "base_score": 4.9,
            "direction_mismatch_adjustment": -0.55,
        }
        aligned = {
            "id": 2,
            "company": "Product Studio",
            "position": "Product Intern",
            "source": "InternSG",
            "status": "Recommended",
            "batch_date": older_date,
            "score": 4.0,
            "rank_score": 4.2,
            "base_score": 4.0,
            "direction_mismatch_adjustment": 0.0,
        }

        payload = server.recommendation_payload_from_ranked_jobs(
            [mismatched, aligned],
            "SG",
            2,
            {},
            ["ux_product_design"],
            "user_selected",
            [],
        )

        self.assertEqual([job["id"] for job in payload["jobs"]], [2, 1])

    def test_workbench_diversifies_sources_and_fills_when_alternatives_are_insufficient(self):
        jobs = [
            {"id": index, "company": f"Company {index}", "source": source, "score": 5 - index / 100}
            for index, source in enumerate(["Source A"] * 10 + ["Source B"] * 4 + ["Source C"] * 4 + ["Source D"] * 4, 1)
        ]

        diversified = server.diversified_workbench_recommendations(jobs, set(), 10)
        only_one_source = server.diversified_workbench_recommendations(jobs[:8], set(), 8)

        source_counts = {}
        for job in diversified:
            source_counts[job["source"]] = source_counts.get(job["source"], 0) + 1
        self.assertEqual(len(diversified), 10)
        self.assertLessEqual(max(source_counts.values()), 3)
        self.assertEqual(len(only_one_source), 8)

    def test_workbench_never_backfills_more_than_two_jobs_from_one_company(self):
        jobs = [
            {"id": index, "company": "Focused Company", "source": f"Source {index}", "score": 5 - index / 100}
            for index in range(1, 7)
        ]

        selected = server.diversified_workbench_recommendations(jobs, set(), 6)

        self.assertEqual([job["id"] for job in selected], [1, 2])

    def test_weekly_bucket_ranks_by_fit_instead_of_inherited_freshness_order(self):
        lower_fit_today = {
            "id": 1,
            "company": "Today Finance Co",
            "source": "ATS",
            "status": "Recommended",
            "found_date": server.today(),
            "rank_score": 3.4,
            "base_score": 3.1,
        }
        stronger_older = {
            "id": 2,
            "company": "Strong Product Co",
            "source": "InternSG",
            "status": "Recommended",
            "found_date": (server.dt.date.today() - server.dt.timedelta(days=3)).strftime(server.DATE_FMT),
            "rank_score": 4.8,
            "base_score": 4.2,
        }

        selected = server.workbench_recommendation_bucket(
            [lower_fit_today, stronger_older],
            set(),
            limit=1,
            max_age_days=6,
        )

        self.assertEqual([job["id"] for job in selected], [2])
    def test_compact_job_payload_keeps_list_fields_and_omits_full_jd(self):
        job = server.upsert_job(
            {
                "company": "Compact Co",
                "position": "Product Design Intern",
                "source": "LinkedIn",
                "url": "https://example.com/compact-job",
                "jd_text": "Singapore product design internship. " * 200,
            }
        )
        with server.get_db() as conn:
            conn.execute("update jobs set score=4.6, status='Recommended' where id=?", (job["id"],))

        full = server.list_jobs_payload({"region": ["SG"]})
        compact = server.list_jobs_payload({"region": ["SG"], "compact": ["1"]})
        full_job = next(item for item in full if item["id"] == job["id"])
        compact_job = next(item for item in compact if item["id"] == job["id"])

        self.assertIn("jd_text", full_job)
        self.assertNotIn("jd_text", compact_job)
        self.assertNotIn("jd_cn_text", compact_job)
        self.assertNotIn("score_breakdown", compact_job)
        self.assertNotIn("fit_reasons", compact_job)
        self.assertNotIn("pathway_questions", compact_job)
        self.assertNotIn("pathway_evidence_json", compact_job)
        self.assertNotIn("resume_path", compact_job)
        self.assertNotIn("cover_letter_path", compact_job)
        self.assertEqual(compact_job["company"], "Compact Co")
        self.assertEqual(compact_job["fit_score"], full_job["fit_score"])
        self.assertEqual(compact_job["url"], full_job["url"])
        self.assertLessEqual(len(compact_job), 65)

    def test_low_score_user_state_jobs_survive_recommendation_pool_limit(self):
        stamp = server.now_iso()
        day = server.today()
        with server.get_db() as conn:
            conn.executemany(
                """
                insert into jobs(
                    company, position, name, source, url, location, jd_text, jd_hash,
                    score, status, found_date, last_checked_at, created_at, updated_at,
                    region, city, source_region
                ) values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        f"Pool Company {index}", "Product Intern", f"Pool Company {index} - Product Intern",
                        "Fixture", f"https://example.com/pool-{index}", "Singapore", "Singapore product internship.",
                        f"pool-{index}", 5.0, "Recommended", day, stamp, stamp, stamp, "SG", "Singapore", "SG",
                    )
                    for index in range(505)
                ],
            )
            state_ids = {}
            for status in ["Apply Queue", "Applied", "Dropped"]:
                cursor = conn.execute(
                    """
                    insert into jobs(
                        company, position, name, source, url, location, jd_text, jd_hash,
                        score, status, found_date, last_checked_at, created_at, updated_at,
                        region, city, source_region
                    ) values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"State {status}", "Low Score Role", f"State {status} - Low Score Role",
                        "Fixture", f"https://example.com/state-{status.lower().replace(' ', '-')}", "Singapore",
                        "Singapore role retained by user state.", f"state-{status}", 0.1, status,
                        day, stamp, stamp, stamp, "SG", "Singapore", "SG",
                    ),
                )
                state_ids[status] = cursor.lastrowid

        jobs = server.list_jobs({"region": ["SG"], "city": ["Singapore"]})
        returned_ids = {job["id"] for job in jobs}
        self.assertTrue(set(state_ids.values()).issubset(returned_ids))

        payload = server.workbench_payload({"region": ["SG"], "city": ["Singapore"]})
        queue_action = next(item for item in payload["today_actions"] if item["kind"] == "queue")
        self.assertEqual(payload["summary"]["apply_queue"], 1)
        self.assertIn("1 个岗位", queue_action["title"])

    def test_workbench_payload_is_stable_when_empty(self):
        payload = server.workbench_payload({"region": ["SG"]})

        self.assertEqual(payload["region"], "SG")
        self.assertIn("summary", payload)
        self.assertIn("today_actions", payload)
        self.assertEqual(payload["top_recommendations"], [])
        self.assertEqual(payload["today_new_recommendations"], [])
        self.assertEqual(payload["weekly_unqueued_recommendations"], [])
        self.assertEqual(payload["discovery_summary"]["today_discovered"], 0)
        self.assertEqual(payload["discovery_summary"]["today_actionable"], 0)
        self.assertEqual(payload["recommendation_sections"][0]["id"], "today_new")
        self.assertEqual(payload["recommendation_sections"][1]["id"], "weekly_unqueued")
        self.assertEqual(payload["queue_preview"], [])
        self.assertEqual(payload["followups"], [])
        self.assertEqual(payload["followup_count"], 0)
        self.assertEqual(payload["stale_application_count"], 0)
        self.assertEqual(payload["scan_overview"]["status"], "pending")

    def test_workbench_reports_full_followup_count_separately_from_preview(self):
        applied_date = (server.dt.date.today() - server.dt.timedelta(days=8)).strftime(server.DATE_FMT)
        for index in range(7):
            job = server.upsert_job(
                {
                    "company": f"Followup Co {index}",
                    "position": "Product Intern",
                    "source": "LinkedIn",
                    "url": f"https://example.com/followup-{index}",
                    "jd_text": "Singapore product internship.",
                }
            )
            with server.get_db() as conn:
                conn.execute(
                    "update jobs set status='Applied', applied_date=? where id=?",
                    (applied_date, job["id"]),
                )

        payload = server.workbench_payload({"region": ["SG"]})

        self.assertEqual(payload["followup_count"], 7)
        self.assertEqual(len(payload["followups"]), 5)

    def test_workbench_separates_long_unanswered_applications_from_followups(self):
        due_date = (server.dt.date.today() - server.dt.timedelta(days=7)).strftime(server.DATE_FMT)
        stale_date = (server.dt.date.today() - server.dt.timedelta(days=20)).strftime(server.DATE_FMT)
        due_job = server.upsert_job({"company": "Due Co", "position": "UX Intern", "source": "LinkedIn", "url": "https://example.com/due", "jd_text": "Singapore UX internship."})
        stale_job = server.upsert_job({"company": "Stale Co", "position": "Product Intern", "source": "LinkedIn", "url": "https://example.com/stale", "jd_text": "Singapore product internship."})
        with server.get_db() as conn:
            conn.execute("update jobs set status='Applied', applied_date=? where id=?", (due_date, due_job["id"]))
            conn.execute("update jobs set status='Applied', applied_date=? where id=?", (stale_date, stale_job["id"]))

        payload = server.workbench_payload({"region": ["SG"]})

        self.assertEqual(payload["followup_count"], 1)
        self.assertEqual(payload["stale_application_count"], 1)
        self.assertIn(due_job["id"], [job["id"] for job in payload["followups"]])
        self.assertNotIn(stale_job["id"], [job["id"] for job in payload["followups"]])
        self.assertIn("最后确认一次后归档", server.next_step_for_job(server.get_job(stale_job["id"])))

    def test_recorded_followup_temporarily_clears_reminder_and_second_followup_can_become_stale(self):
        applied_date = (server.dt.date.today() - server.dt.timedelta(days=20)).strftime(server.DATE_FMT)
        job = server.upsert_job({"company": "Follow Through Co", "position": "Product Intern", "source": "LinkedIn", "url": "https://example.com/follow-through", "jd_text": "Singapore product internship."})
        with server.get_db() as conn:
            conn.execute("update jobs set status='Applied', applied_date=? where id=?", (applied_date, job["id"]))

        first = server.set_decision(job["id"], "FollowUpSent")
        self.assertEqual(first["followup_count"], 1)
        self.assertEqual(first["last_followup_at"], server.today())
        self.assertEqual(server.application_action_bucket(first), "waiting")
        self.assertIn("等待反馈", server.next_step_for_job(first))

        old_followup = (server.dt.date.today() - server.dt.timedelta(days=8)).strftime(server.DATE_FMT)
        with server.get_db() as conn:
            conn.execute("update jobs set last_followup_at=?, followup_count=2 where id=?", (old_followup, job["id"]))
        self.assertEqual(server.application_action_bucket(server.get_job(job["id"])), "stale")

        paused = server.set_decision(job["id"], "Pause")
        self.assertEqual(paused["status"], "Closed")

    def test_workbench_recommendations_do_not_embed_full_job_descriptions(self):
        job = server.upsert_job(
            {
                "company": "Lean Workbench Co",
                "position": "AI Product Intern",
                "source": "InternSG",
                "url": "https://example.com/lean-workbench",
                "jd_text": "Singapore AI product internship with conversion potential. " * 200,
            }
        )
        with server.get_db() as conn:
            conn.execute("update jobs set score=4.8, status='Recommended' where id=?", (job["id"],))

        payload = server.workbench_payload({"region": ["SG"]})
        recommendation = next(item for item in payload["top_recommendations"] if item["id"] == job["id"])

        self.assertNotIn("jd_text", recommendation)
        self.assertNotIn("jd_cn_text", recommendation)
        self.assertIn("recommendation_reason", recommendation)

    def test_workbench_uses_lightweight_job_rows_and_defers_supplemental_pool(self):
        job = server.upsert_job(
            {
                "company": "Lean Payload Co",
                "position": "Product Research Intern",
                "source": "Company Site / ATS",
                "url": "https://example.com/lean-payload",
                "jd_text": "Singapore product research internship with conversion potential. " * 200,
            }
        )
        with server.get_db() as conn:
            conn.execute("update jobs set score=4.8, status='Recommended' where id=?", (job["id"],))

        payload = server.workbench_payload({"region": ["SG"]})
        recommendation = next(item for item in payload["today_new_recommendations"] if item["id"] == job["id"])

        self.assertEqual(payload["recommendations"]["jobs"], [])
        self.assertIn("recommendation_reason", recommendation)
        self.assertIn("user_tag_matches", recommendation)
        self.assertNotIn("resume_path", recommendation)
        self.assertNotIn("cover_letter_path", recommendation)
        self.assertNotIn("score_breakdown", recommendation)
        self.assertNotIn("fit_reasons", recommendation)
        self.assertNotIn("matched_directions", recommendation)
        self.assertLessEqual(len(recommendation), 36)

        full_job = server.job_payload(server.get_job(job["id"]))
        self.assertIn("jd_text", full_job)
        self.assertGreater(len(full_job["jd_text"]), 1000)

    def test_workbench_ranks_each_job_only_once(self):
        for index in range(4):
            job = server.upsert_job(
                {
                    "company": f"Single Pass Co {index}",
                    "position": "Product Intern",
                    "source": "InternSG",
                    "url": f"https://example.com/single-pass-{index}",
                    "jd_text": "Singapore product internship with UX research.",
                }
            )
            with server.get_db() as conn:
                conn.execute("update jobs set score=4.2, status='Recommended' where id=?", (job["id"],))

        with mock.patch.object(server, "rank_job_with_preferences", wraps=server.rank_job_with_preferences) as rank_job:
            server.workbench_payload({"region": ["SG"]})

        self.assertEqual(rank_job.call_count, 4)

    def test_recommendations_collapse_duplicate_roles_and_preserve_all_links(self):
        duplicate_ids = []
        for source, url in [
            ("LinkedIn", "https://www.linkedin.com/jobs/view/4440000001"),
            ("JobStreet", "https://sg.jobstreet.com/job/94400001"),
            ("Indeed", "https://sg.indeed.com/viewjob?jk=duplicate-role"),
        ]:
            job = server.upsert_job(
                {
                    "company": "Duplicate Role Co",
                    "position": "AI Product Intern",
                    "source": source,
                    "url": url,
                    "jd_text": "Singapore AI product internship with UX research.",
                }
            )
            duplicate_ids.append(job["id"])
            with server.get_db() as conn:
                conn.execute("update jobs set score=4.9, status='Recommended' where id=?", (job["id"],))
        for index in range(3):
            job = server.upsert_job(
                {
                    "company": f"Unique Role Co {index}",
                    "position": f"Product Design Intern {index}",
                    "source": "InternSG",
                    "url": f"https://example.com/unique-role-{index}",
                    "jd_text": "Singapore product design internship.",
                }
            )
            with server.get_db() as conn:
                conn.execute("update jobs set score=4.2, status='Recommended' where id=?", (job["id"],))

        payload = server.list_today_recommendations({"region": ["SG"], "limit": ["4"]})
        jobs = payload["jobs"]
        duplicate_job = next(job for job in jobs if job["company"] == "Duplicate Role Co")

        self.assertEqual(len(jobs), 4)
        self.assertEqual(sum(1 for job in jobs if job["company"] == "Duplicate Role Co"), 1)
        self.assertEqual(duplicate_job["duplicate_count"], 2)
        self.assertEqual({item["id"] for item in duplicate_job["alternate_links"]}, set(duplicate_ids) - {duplicate_job["id"]})
        self.assertEqual(len({job["dedupe_key"] for job in jobs}), 4)

    def test_dedupe_collapses_cpf_legal_name_variants(self):
        jobs = server.collapse_duplicate_job_groups([
            {
                "id": 1,
                "region": "SG",
                "city": "Singapore",
                "company": "CPF Board",
                "position": "GenAI Product Development Intern",
                "source": "LinkedIn",
                "url": "https://www.linkedin.com/jobs/view/1",
            },
            {
                "id": 2,
                "region": "SG",
                "city": "Singapore",
                "company": "Central Provident Fund Board",
                "position": "GenAI Product Development Intern",
                "source": "Careers@Gov",
                "url": "https://jobs.careers.gov.sg/jobs/2",
            },
        ])

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["source_count"], 2)
        self.assertEqual(jobs[0]["alternate_links"][0]["id"], 2)

    def test_workbench_payload_surfaces_actions_queue_followups_and_limited_scan(self):
        recommendation = server.upsert_job(
            {
                "company": "Pathway Co",
                "position": "AI Product Intern",
                "source": "Company Site / ATS",
                "url": "https://example.com/workbench-rec",
                "jd_text": "Singapore AI product internship with possible full-time conversion and Mandarin market work.",
            }
        )
        queue_job = server.upsert_job(
            {
                "company": "Queue Co",
                "position": "UX Intern",
                "source": "InternSG",
                "url": "https://example.com/workbench-queue",
                "jd_text": "Singapore UX internship.",
            }
        )
        applied_job = server.upsert_job(
            {
                "company": "Applied Co",
                "position": "Product Ops Intern",
                "source": "LinkedIn",
                "url": "https://example.com/workbench-applied",
                "jd_text": "Singapore product operations internship.",
            }
        )
        old_applied = (server.dt.date.today() - server.dt.timedelta(days=5)).strftime(server.DATE_FMT)
        with server.get_db() as conn:
            conn.execute("update jobs set score=4.4, status='Recommended' where id=?", (recommendation["id"],))
            conn.execute("update jobs set score=4.1, status='Apply Queue' where id=?", (queue_job["id"],))
            conn.execute("update jobs set score=4.0, status='Applied', applied_date=? where id=?", (old_applied, applied_job["id"]))
        run_id = server.create_scan_run("manual", True, "SG")
        server.finish_scan_run(run_id, "partial", 10, 8, 3, 1, [{"source": "JobStreet", "error": "limited"}])

        payload = server.workbench_payload({"region": ["SG"]})
        action_kinds = [item["kind"] for item in payload["today_actions"]]

        self.assertIn(recommendation["id"], [job["id"] for job in payload["top_recommendations"]])
        self.assertIn(recommendation["id"], [job["id"] for job in payload["today_new_recommendations"]])
        self.assertIn(queue_job["id"], [job["id"] for job in payload["queue_preview"]])
        self.assertIn(applied_job["id"], [job["id"] for job in payload["followups"]])
        self.assertIn("recommendations", action_kinds)
        self.assertIn("queue", action_kinds)
        self.assertIn("followup", action_kinds)
        self.assertEqual(payload["scan_overview"]["status"], "partial")
        self.assertGreater(payload["scan_overview"]["failure_count"], 0)

    def test_workbench_scan_overview_reports_job_quality_counts(self):
        run_id = server.create_scan_run("manual", True, "SG")
        source_run_id = server.create_scan_source_run(run_id, "LinkedIn")
        server.finish_scan_source_run(
            source_run_id,
            "partial",
            12,
            9,
            [{"error": "one limited result"}],
            5,
            4,
            3,
        )
        server.finish_scan_run(
            run_id,
            "partial",
            12,
            9,
            3,
            1,
            [{"source": "LinkedIn", "error": "one limited result"}],
            5,
            4,
            3,
        )

        overview = server.workbench_payload({"region": ["SG"]})["scan_overview"]
        linkedin = next(row for row in overview["sources"] if row["source"] == "LinkedIn")

        self.assertEqual(overview["new_count"], 5)
        self.assertEqual(overview["updated_count"], 4)
        self.assertEqual(overview["duplicate_count"], 3)
        self.assertIn("5 条新发现", overview["summary"])
        self.assertEqual(linkedin["new_count"], 5)
        self.assertEqual(linkedin["updated_count"], 4)
        self.assertEqual(linkedin["duplicate_count"], 3)

    def test_workbench_returns_twenty_priority_jobs_and_excludes_watched_company_jobs(self):
        with server.get_db() as conn:
            conn.execute(
                """
                insert into watch_companies(company, source, url, focus, region, status)
                values(?, ?, ?, ?, ?, ?)
                on conflict(region, company) do update set status='Watch'
                """,
                ("TikTok", "Company Site", "https://careers.tiktok.com/", "Product", "SG", "Watch"),
            )
        for index in range(10):
            job = server.upsert_job(
                {
                    "company": "TikTok",
                    "position": f"Product Intern {index}",
                    "source": "LinkedIn",
                    "url": f"https://example.com/tiktok-{index}",
                    "jd_text": "Singapore product internship with Mandarin market work.",
                }
            )
            with server.get_db() as conn:
                conn.execute("update jobs set score=4.9, status='Recommended' where id=?", (job["id"],))
        for index in range(24):
            job = server.upsert_job(
                {
                    "company": f"Balanced Co {index}",
                    "position": "Product Intern",
                    "source": "InternSG",
                    "url": f"https://example.com/balanced-{index}",
                    "jd_text": "Singapore product internship.",
                }
            )
            with server.get_db() as conn:
                conn.execute("update jobs set score=4.2, status='Recommended' where id=?", (job["id"],))

        payload = server.workbench_payload({"region": ["SG"]})
        priority_companies = [job["company"] for job in payload["top_recommendations"]]

        self.assertEqual(len(payload["top_recommendations"]), 20)
        self.assertEqual(payload["watched_company_jobs"], [])
        self.assertNotIn("TikTok", priority_companies)

    def test_workbench_splits_today_and_weekly_unqueued_recommendations(self):
        current_date = server.today()
        week_date = (server.dt.date.today() - server.dt.timedelta(days=3)).strftime(server.DATE_FMT)
        old_date = (server.dt.date.today() - server.dt.timedelta(days=8)).strftime(server.DATE_FMT)
        today_ids = []
        weekly_ids = []
        for index in range(24):
            job = server.upsert_job(
                {
                    "company": f"Today Co {index}",
                    "position": "Product Intern",
                    "source": "InternSG",
                    "url": f"https://example.com/today-bucket-{index}",
                    "jd_text": "Singapore product internship with possible full-time conversion.",
                }
            )
            today_ids.append(job["id"])
            with server.get_db() as conn:
                conn.execute(
                    "update jobs set score=4.6, status='Recommended', found_date=?, batch_date=?, recommended_date=? where id=?",
                    (current_date, current_date, current_date, job["id"]),
                )
        for index in range(25):
            job = server.upsert_job(
                {
                    "company": f"Weekly Co {index}",
                    "position": "UX Intern",
                    "source": "LinkedIn",
                    "url": f"https://example.com/weekly-bucket-{index}",
                    "jd_text": "Singapore UX internship with research and product work.",
                }
            )
            weekly_ids.append(job["id"])
            with server.get_db() as conn:
                conn.execute(
                    "update jobs set score=4.3, status='Recommended', found_date=?, batch_date=?, recommended_date=? where id=?",
                    (week_date, week_date, week_date, job["id"]),
                )
        queue_job = server.upsert_job(
            {
                "company": "Queued Weekly Co",
                "position": "Product Intern",
                "source": "InternSG",
                "url": "https://example.com/weekly-queued",
                "jd_text": "Singapore product internship.",
            }
        )
        applied_job = server.upsert_job(
            {
                "company": "Applied Weekly Co",
                "position": "Product Intern",
                "source": "InternSG",
                "url": "https://example.com/weekly-applied",
                "jd_text": "Singapore product internship.",
            }
        )
        old_job = server.upsert_job(
            {
                "company": "Old Weekly Co",
                "position": "Product Intern",
                "source": "InternSG",
                "url": "https://example.com/weekly-old",
                "jd_text": "Singapore product internship.",
            }
        )
        with server.get_db() as conn:
            conn.execute(
                "update jobs set score=4.7, status='Apply Queue', found_date=?, batch_date=?, recommended_date=? where id=?",
                (week_date, week_date, week_date, queue_job["id"]),
            )
            conn.execute(
                "update jobs set score=4.7, status='Applied', found_date=?, batch_date=?, recommended_date=?, applied_date=? where id=?",
                (week_date, week_date, week_date, week_date, applied_job["id"]),
            )
            conn.execute(
                "update jobs set score=4.7, status='Recommended', found_date=?, batch_date=?, recommended_date=? where id=?",
                (old_date, old_date, old_date, old_job["id"]),
            )

        payload = server.workbench_payload({"region": ["SG"]})
        today_bucket_ids = [job["id"] for job in payload["today_new_recommendations"]]
        weekly_bucket_ids = [job["id"] for job in payload["weekly_unqueued_recommendations"]]

        self.assertEqual(len(today_bucket_ids), 20)
        self.assertEqual(len(weekly_bucket_ids), 20)
        self.assertTrue(set(today_bucket_ids).issubset(set(today_ids)))
        self.assertTrue(set(weekly_bucket_ids).issubset(set(today_ids + weekly_ids)))
        self.assertFalse(set(today_bucket_ids).intersection(weekly_bucket_ids))
        self.assertNotIn(queue_job["id"], weekly_bucket_ids)
        self.assertNotIn(applied_job["id"], weekly_bucket_ids)
        self.assertNotIn(old_job["id"], weekly_bucket_ids)
        self.assertEqual(payload["recommendation_sections"][0]["count"], 20)
        self.assertEqual(payload["recommendation_sections"][1]["count"], 20)
        self.assertGreaterEqual(payload["discovery_summary"]["today_discovered"], 24)
        self.assertGreaterEqual(payload["discovery_summary"]["today_actionable"], 20)

    def test_weekly_bucket_excludes_a_title_variant_already_shown_today(self):
        current_date = server.today()
        week_date = (server.dt.date.today() - server.dt.timedelta(days=3)).strftime(server.DATE_FMT)
        today_job = server.upsert_job(
            {
                "company": "Duplicate AI Co",
                "position": "Python Developer",
                "source": "LinkedIn",
                "url": "https://example.com/python-today",
                "jd_text": "Singapore Python and AI role.",
            }
        )
        weekly_job = server.upsert_job(
            {
                "company": "Duplicate AI Co",
                "position": "Python Developer (AI / LLM / RAG)",
                "source": "JobStreet",
                "url": "https://example.com/python-weekly",
                "jd_text": "Singapore Python and AI role.",
            }
        )
        with server.get_db() as conn:
            conn.execute(
                "update jobs set score=4.5, status='Recommended', found_date=?, batch_date=?, recommended_date=? where id=?",
                (current_date, current_date, current_date, today_job["id"]),
            )
            conn.execute(
                "update jobs set score=4.5, status='Recommended', found_date=?, batch_date=?, recommended_date=? where id=?",
                (week_date, week_date, week_date, weekly_job["id"]),
            )

        payload = server.workbench_payload({"region": ["SG"]})

        self.assertIn(today_job["id"], [job["id"] for job in payload["today_new_recommendations"]])
        self.assertNotIn(weekly_job["id"], [job["id"] for job in payload["weekly_unqueued_recommendations"]])


class RecommendationTests(TempAppMixin, unittest.TestCase):
    def test_decision_summary_is_plain_language_and_keeps_the_key_pathway_tradeoff(self):
        summary = server.job_decision_summary({
            "employment_type": "Internship",
            "matched_directions": [{"label": "UX/Product Design", "keywords": ["figma", "prototype"]}],
            "conversion_signal": "possible",
            "visa_sponsorship_signal": "unclear",
            "language_signal": "chinese_friendly_possible",
            "listing_freshness_status": "fresh",
            "source": "ATS",
            "source_count": 2,
            "user_tag_mutes": [],
            "direction_mismatch_adjustment": 0,
        })

        self.assertIn("实习", summary)
        self.assertIn("UX/Product Design", summary)
        self.assertIn("转正", summary)
        self.assertIn("工签需确认", summary)
        self.assertNotIn("figma", summary.lower())
        self.assertNotIn(":", summary)
        self.assertLessEqual(len(summary), 72)

    def test_ranked_job_and_workbench_payload_include_decision_summary(self):
        ranked = server.rank_job_with_preferences({
            "id": 99,
            "company": "Clear Choice",
            "position": "Product Design Intern",
            "source": "Company ATS",
            "url": "https://example.com/product-design-intern",
            "status": "Recommended",
            "score": 4.4,
            "region": "SG",
            "source_region": "SG",
            "city": "Singapore",
            "location": "Singapore",
            "found_date": server.today(),
            "last_checked_at": server.now_iso(),
            "updated_at": server.now_iso(),
            "eligibility_flags": [],
            "employment_type": "Internship",
            "conversion_signal": "possible",
            "visa_sponsorship_signal": "unclear",
            "language_signal": "unknown",
        }, ["ux-product-design"], {"ux-product-design": 1.0}, "SG", set(), server.active_region_context("SG"))

        self.assertTrue(ranked["decision_summary"])
        self.assertEqual(server.workbench_job_payload(ranked)["decision_summary"], ranked["decision_summary"])

    def test_listing_freshness_excludes_old_unverified_linkedin_but_keeps_internsg_with_penalty(self):
        stale_date = (server.dt.date.today() - server.dt.timedelta(days=35)).strftime(server.DATE_FMT)
        common = {
            "company": "Freshness Co",
            "position": "Product Design Intern",
            "status": "Recommended",
            "score": 4.5,
            "region": "SG",
            "source_region": "SG",
            "city": "Singapore",
            "location": "Singapore",
            "found_date": stale_date,
            "last_checked_at": f"{stale_date}T08:00:00",
            "updated_at": f"{stale_date}T08:00:00",
            "eligibility_flags": [],
            "employment_type": "Internship",
        }
        linkedin = {**common, "source": "LinkedIn", "url": "https://www.linkedin.com/jobs/view/123"}
        internsg = {**common, "source": "InternSG", "url": "https://www.internsg.com/job/product-design-intern/"}

        self.assertEqual(server.job_listing_freshness(linkedin)["status"], "likely_closed")
        self.assertFalse(server.is_recommendation_available(linkedin))
        self.assertEqual(server.job_listing_freshness(internsg)["status"], "verify")
        self.assertTrue(server.is_recommendation_available(internsg))

        ranked = server.rank_job_with_preferences(internsg, [], {}, "SG", set(), server.active_region_context("SG"))
        self.assertEqual(ranked["listing_freshness_label"], "需确认有效")
        self.assertLess(ranked["freshness_adjustment"], 0)
        self.assertEqual(ranked["score_breakdown"]["freshness"], ranked["freshness_adjustment"])

    def test_recent_verification_restores_an_old_discovered_job(self):
        old_date = (server.dt.date.today() - server.dt.timedelta(days=60)).strftime(server.DATE_FMT)
        job = {
            "company": "Still Hiring Co",
            "position": "Product Intern",
            "source": "LinkedIn",
            "url": "https://www.linkedin.com/jobs/view/456",
            "status": "Recommended",
            "score": 4.2,
            "region": "SG",
            "source_region": "SG",
            "city": "Singapore",
            "location": "Singapore",
            "found_date": old_date,
            "last_checked_at": server.now_iso(),
            "updated_at": server.now_iso(),
            "eligibility_flags": [],
            "employment_type": "Internship",
        }

        freshness = server.job_listing_freshness(job)

        self.assertEqual(freshness["status"], "verified")
        self.assertEqual(freshness["label"], "今日已验证")
        self.assertEqual(freshness["adjustment"], 0)
        self.assertTrue(server.is_recommendation_available(job))

    def test_strong_retention_pathway_can_rescue_a_near_threshold_internship(self):
        pathway_job = server.upsert_job(
            {
                "company": "Conversion Studio",
                "position": "Creative Intern",
                "source": "Cultjobs",
                "url": "https://example.com/pathway-rescue",
                "jd_text": "Singapore creative internship with a potential opportunity for full-time conversion.",
            }
        )
        ordinary_low = server.upsert_job(
            {
                "company": "Ordinary Studio",
                "position": "Creative Intern",
                "source": "Cultjobs",
                "url": "https://example.com/ordinary-low",
                "jd_text": "Singapore creative internship.",
            }
        )
        hard_blocked = server.upsert_job(
            {
                "company": "Local Only Studio",
                "position": "Creative Intern",
                "source": "Cultjobs",
                "url": "https://example.com/pathway-blocked",
                "jd_text": "Singapore creative internship with full-time conversion. Singapore citizens and PR only.",
            }
        )
        with server.get_db() as conn:
            conn.execute("update jobs set score=2.8, status='New' where id in (?, ?, ?)", (pathway_job["id"], ordinary_low["id"], hard_blocked["id"]))

        pathway = server.get_job(pathway_job["id"])
        ordinary = server.get_job(ordinary_low["id"])
        blocked = server.get_job(hard_blocked["id"])

        self.assertTrue(server.is_pathway_recommendation_candidate(pathway))
        self.assertTrue(server.is_recommendation_available(pathway))
        self.assertFalse(server.is_pathway_recommendation_candidate(ordinary))
        self.assertFalse(server.is_recommendation_available(ordinary))
        self.assertFalse(server.is_recommendation_available(blocked))
        recommendations = server.list_today_recommendations({"region": ["SG"], "limit": ["20"]})["jobs"]
        ranked = next(job for job in recommendations if job["id"] == pathway_job["id"])
        self.assertTrue(ranked["pathway_candidate"])
        self.assertIn("留新路径补充候选", ranked["recommendation_reason"])

    def test_pathway_pool_is_not_lost_below_the_primary_five_hundred_row_cutoff(self):
        pathway_job = server.upsert_job(
            {
                "company": "Deep Pathway Co",
                "position": "Marketing Intern",
                "source": "Cultjobs",
                "url": "https://example.com/deep-pathway",
                "jd_text": "Singapore internship with full-time conversion opportunity.",
            }
        )
        stamp = server.now_iso()
        rows = [
            (
                f"High Score Co {index}", "Product Intern", f"High Score Co {index} - Product Intern",
                "LinkedIn", f"https://example.com/high-score-{index}", "Singapore product internship.",
                f"hash-{index}", 4.0, "Recommended", server.today(), stamp, stamp, stamp,
            )
            for index in range(500)
        ]
        with server.get_db() as conn:
            conn.execute("update jobs set score=2.8, status='New' where id=?", (pathway_job["id"],))
            conn.executemany(
                """
                insert into jobs(company, position, name, source, url, jd_text, jd_hash, score, status, found_date, last_checked_at, created_at, updated_at)
                values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

        jobs = server.list_jobs({"region": ["SG"]})

        self.assertEqual(len(jobs), 501)
        self.assertIn(pathway_job["id"], [job["id"] for job in jobs])

    def test_today_recommendations_include_fresh_jobs_below_the_primary_row_cutoff(self):
        common = {
            "source": "Company Site / ATS",
            "status": "Recommended",
            "score": 3.5,
            "rank_score": 3.5,
            "base_score": 3.5,
            "region": "SG",
            "city": "Singapore",
            "location": "Singapore",
            "employment_type": "Internship",
            "eligibility_flags": [],
            "found_date": server.today(),
        }
        primary = {**common, "id": 1, "company": "Primary Co", "position": "Product Intern"}
        fresh = {**common, "id": 2, "company": "Fresh Co", "position": "Analytics Intern"}

        def jobs_fixture(params):
            return [fresh] if params.get("date") else [primary]

        with mock.patch.object(server, "list_jobs", side_effect=jobs_fixture):
            with mock.patch.object(server, "apply_preference_scores_to_jobs", side_effect=lambda jobs, _region: jobs):
                payload = server.list_today_recommendations({"region": ["SG"], "limit": ["20"]})

        self.assertEqual({job["id"] for job in payload["jobs"]}, {1, 2})

    def test_unknown_internship_pathway_generates_confirmation_tags_and_questions(self):
        pathway = server.pathway_preference_for_job(
            {
                "company": "Unclear Internship Co",
                "position": "Product Intern",
                "employment_type": "Internship",
                "conversion_signal": "unknown",
                "visa_sponsorship_signal": "unknown",
                "language_signal": "unknown",
            },
            {
                "career_goal": "sg_internship_to_fulltime",
                "conversion_priority": "high",
                "sponsorship_priority": "high",
                "language_preference": "chinese_friendly",
                "preferred_company_groups": [],
            },
            "SG",
        )

        self.assertIn("转正待确认", pathway["pathway_tags"])
        self.assertIn("工签待确认", pathway["pathway_tags"])
        self.assertTrue(any("return offer" in item for item in pathway["pathway_questions"]))
        self.assertTrue(any("EP 或 S Pass" in item for item in pathway["pathway_questions"]))

    def test_navigation_titles_are_not_recommendable_jobs(self):
        common = {
            "company": "Example Co",
            "status": "Recommended",
            "score": 4.5,
            "eligibility_flags": [],
        }

        for title in ["View all product jobs", "Careers", "Careers at Hypotenuse AI", "Open positions"]:
            with self.subTest(title=title):
                self.assertFalse(server.is_recommendation_available({**common, "position": title}))

        self.assertTrue(server.is_recommendation_available({**common, "position": "Career Up Intern"}))
        self.assertTrue(server.is_recommendation_available({**common, "position": "Careers Consultant Intern"}))
        self.assertFalse(server.is_recommendation_available({**common, "company": "Glints / NodeFlair / Startups", "position": "Product Designer"}))
        self.assertFalse(server.is_recommendation_available({**common, "company": "UI / UX Design Intern", "position": "UI / UX Design Intern"}))

    def test_company_site_navigation_links_do_not_become_jobs(self):
        navigation = server.company_job_record(
            "Example AI",
            "Careers at Example AI",
            "/careers",
            "SG",
            "Singapore",
            "AI / Product",
            "https://example.com/careers",
            "Careers at Example AI",
        )
        role = server.company_job_record(
            "Example AI",
            "Software Engineer Intern",
            "/jobs/software-engineer-intern",
            "SG",
            "Singapore",
            "AI / Product",
            "https://example.com/careers",
            "Build AI product experiences with the product team.",
        )

        self.assertIsNone(navigation)
        self.assertIsNotNone(role)
        for fake_title in ["Product Development Agency", "AI Chatbot", "Design FTO Search", "Engineering Agents", "Developer Center"]:
            with self.subTest(fake_title=fake_title):
                self.assertIsNone(
                    server.company_job_record(
                        "Example AI",
                        fake_title,
                        "/services/example",
                        "SG",
                        "Singapore",
                        "AI / Product",
                        "https://example.com/careers",
                        fake_title,
                    )
                )
        self.assertIsNone(
            server.company_job_record(
                "Example AI",
                "Back-End Developer " + ("Design and operate reliable services. " * 8),
                "/services/backend",
                "SG",
                "Singapore",
                "AI / Product",
                "https://example.com/careers",
                "Backend services",
            )
        )

    def test_company_jobs_exclude_legacy_navigation_and_regulatory_rows(self):
        fake = server.upsert_job(
            {
                "company": "PDD",
                "position": "沪ICP备2024094620号-2",
                "source": "Company Site",
                "url": "https://beian.miit.gov.cn/",
                "location": "Singapore",
                "jd_text": "PDD official career page footer.",
            }
        )
        real = server.upsert_job(
            {
                "company": "PDD",
                "position": "Product Design Intern",
                "source": "Company Site",
                "url": "https://example.com/pdd-product-intern",
                "location": "Singapore",
                "jd_text": "Singapore product design internship.",
            }
        )

        payload = server.company_jobs_payload("PDD", "SG", "Singapore")
        ids = [job["id"] for job in payload["jobs"]]

        self.assertNotIn(fake["id"], ids)
        self.assertIn(real["id"], ids)

    def test_pdd_official_roles_require_explicit_singapore_location(self):
        common = {
            "company": "PDD",
            "title": "Product Design Intern",
            "url": "/campus/intern/detail/123",
            "region": "SG",
            "city": "Singapore",
            "focus": "Internship and product roles",
            "source_url": "https://careers.pddglobalhr.com/campus/intern",
            "description": "Product design internship.",
        }

        self.assertIsNone(server.company_job_record(**common))
        self.assertIsNotNone(server.company_job_record(**common, location="Singapore"))
        self.assertIsNone(server.company_job_record(**common, location="Shanghai, China"))

    def test_company_site_jobs_reject_explicit_foreign_locations(self):
        common = {
            "company": "Example AI",
            "title": "Product Engineer Intern",
            "url": "/jobs/product-engineer-intern",
            "region": "SG",
            "city": "Singapore",
            "focus": "AI / Product",
            "source_url": "https://example.com/careers",
            "description": "Build product experiences with the engineering team.",
        }

        self.assertIsNotNone(server.company_job_record(**common, location="Singapore"))
        self.assertIsNotNone(server.company_job_record(**common, location="Jurong"))
        self.assertIsNotNone(server.company_job_record(**common, location="Remote"))
        self.assertIsNone(server.company_job_record(**common, location="Sydney, Australia"))
        self.assertIsNone(server.company_job_record(**common, location="Taipei, Taiwan"))

        recommendation = {
            "company": "Example AI",
            "position": "Product Engineer Intern",
            "status": "Recommended",
            "score": 4.5,
            "eligibility_flags": [],
            "region": "SG",
            "city": "Singapore",
        }
        self.assertTrue(server.is_recommendation_available({**recommendation, "location": "Jurong"}))
        self.assertFalse(server.is_recommendation_available({**recommendation, "location": "Sydney, Australia"}))
        self.assertFalse(server.is_recommendation_available({
            **recommendation,
            "source": "Company Site / ATS",
            "location": "Mexico City, Mexico",
        }))

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
        restored = server.set_decision(dropped["id"], "Restore")
        self.assertEqual(restored["status"], "Recommended")
        self.assertTrue(server.is_recommendation_available(restored))
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

    def test_queue_payload_uses_same_fit_score_as_workbench(self):
        server.save_user_context(
            {
                "active_region": "SG",
                "context": {
                    "employment_priority": "internship",
                    "target_directions": ["ai-product"],
                },
            }
        )
        job = server.upsert_job(
            {
                "company": "Consistent Co",
                "position": "AI Product Intern",
                "source": "JobStreet",
                "url": "https://sg.jobstreet.com/job/score-consistency",
                "jd_text": "Singapore AI product intern LLM workflow automation UX research.",
            }
        )
        with server.get_db() as conn:
            conn.execute("update jobs set score=4.2, status='Recommended' where id=?", (job["id"],))

        workbench_job = next(
            item for item in server.list_today_recommendations({"limit": ["20"], "region": ["SG"]})["jobs"]
            if item["id"] == job["id"]
        )
        server.set_decision(job["id"], "Apply")
        queue_job = next(
            item for item in server.list_jobs_payload({"status": ["Apply Queue"], "region": ["SG"]})
            if item["id"] == job["id"]
        )

        self.assertEqual(queue_job["score"], 4.2)
        self.assertEqual(queue_job["base_score"], workbench_job["base_score"])
        self.assertEqual(queue_job["rank_score"], workbench_job["rank_score"])
        self.assertEqual(queue_job["fit_score"], workbench_job["fit_score"])

    def test_pathway_score_reorders_sg_retention_internships(self):
        server.save_user_context(
            {
                "active_region": "SG",
                "context": {
                    "employment_priority": "internship",
                    "target_directions": ["ai-product"],
                    "career_goal": "sg_internship_to_fulltime",
                    "conversion_priority": "high",
                    "sponsorship_priority": "high",
                    "language_preference": "chinese_friendly",
                    "preferred_company_groups": ["greater_china", "ai_startup"],
                },
            }
        )
        pathway_job = server.upsert_job(
            {
                "company": "Pathway AI Studio",
                "position": "AI Product Intern",
                "source": "Company Site / ATS",
                "url": "https://example.com/pathway-ai-studio-intern",
                "jd_text": "Singapore AI product internship with return offer track, full-time conversion opportunity, Mandarin and Chinese market work, Employment Pass sponsorship support for strong performers.",
            }
        )
        risky_job = server.upsert_job(
            {
                "company": "Generic Studio",
                "position": "AI Product Intern",
                "source": "JobStreet",
                "url": "https://sg.jobstreet.com/job/no-pathway",
                "jd_text": "Singapore AI product internship. No visa sponsorship. No conversion to full-time.",
            }
        )
        with server.get_db() as conn:
            conn.execute("update jobs set score=4.3, status='Recommended' where id in (?, ?)", (pathway_job["id"], risky_job["id"]))

        recommendations = server.list_today_recommendations({"limit": ["20"], "region": ["SG"]})["jobs"]
        pathway_ranked = next(item for item in recommendations if item["id"] == pathway_job["id"])
        risky_ranked = next(item for item in recommendations if item["id"] == risky_job["id"])

        self.assertLess(recommendations.index(pathway_ranked), recommendations.index(risky_ranked))
        self.assertGreater(pathway_ranked["rank_score"], risky_ranked["rank_score"])
        self.assertIn("可转正", pathway_ranked["pathway_tags"])
        self.assertIn("工签可能", pathway_ranked["pathway_tags"])
        self.assertIn("中文友好可能", pathway_ranked["pathway_tags"])

    def test_metadata_backfill_corrects_stale_no_sponsorship_signal(self):
        job = server.upsert_job(
            {
                "company": "No Sponsor Startup",
                "position": "Product Intern",
                "source": "Company Site / ATS",
                "url": "https://example.com/no-sponsor-startup",
                "jd_text": "Singapore internship. Visa sponsorship not available. Opportunity for full-time conversion based on performance.",
            }
        )
        with server.get_db() as conn:
            conn.execute("update jobs set visa_sponsorship_signal='possible', pathway_score=4.5 where id=?", (job["id"],))
            server.backfill_job_metadata(conn)

        corrected = server.get_job(job["id"])
        self.assertEqual(corrected["visa_sponsorship_signal"], "unlikely")
        self.assertLess(corrected["pathway_score"], 4.5)

    def test_metadata_backfill_clears_stale_business_metric_salary(self):
        job = server.upsert_job(
            {
                "company": "Metric AI",
                "position": "Product Intern",
                "source": "Company Site / ATS",
                "url": "https://example.com/metric-ai-intern",
                "jd_text": "The company raised SGD 95 million. Join our Singapore product internship.",
            }
        )
        with server.get_db() as conn:
            conn.execute(
                "update jobs set salary_min=95, salary_max=95, salary_currency='SGD', salary_period='unknown', salary_text='raised SGD 95 million' where id=?",
                (job["id"],),
            )
            server.backfill_job_metadata(conn)

        corrected = server.get_job(job["id"])
        self.assertIsNone(corrected["salary_min"])
        self.assertEqual(corrected["salary_period"], "unknown")
        self.assertEqual(corrected["salary_fit"], "unknown")

    def test_internship_priority_demotes_high_experience_roles(self):
        server.save_user_context(
            {
                "active_region": "SG",
                "context": {
                    "employment_priority": "internship",
                    "career_goal": "sg_internship_to_fulltime",
                },
            }
        )
        intern = server.upsert_job(
            {
                "company": "Good Internship Co",
                "position": "Product Design Intern",
                "source": "InternSG",
                "url": "https://www.internsg.com/job/good-internship/",
                "jd_text": "Singapore product design internship with UX research and prototype work.",
            }
        )
        senior = server.upsert_job(
            {
                "company": "Public Digital Studio",
                "position": "Principal / Lead Designer, Consulting Practice",
                "source": "LinkedIn",
                "url": "https://www.linkedin.com/jobs/view/high-experience-role",
                "jd_text": "Singapore product and UX role. What we are looking for: 10+ years in experience design.",
                "job_type": "Internship / Full-time",
            }
        )
        with server.get_db() as conn:
            conn.execute("update jobs set score=4.0, status='Recommended' where id in (?, ?)", (intern["id"], senior["id"]))

        recommendations = server.list_today_recommendations({"limit": ["20"], "region": ["SG"]})["jobs"]
        intern_ranked = next(item for item in recommendations if item["id"] == intern["id"])
        senior_ranked = next(item for item in recommendations if item["id"] == senior["id"])

        self.assertLess(recommendations.index(intern_ranked), recommendations.index(senior_ranked))
        self.assertEqual(senior_ranked["employment_type"], "Full-time")
        self.assertEqual(senior_ranked["employment_fit_label"], "年限偏高")

    def test_user_selected_tags_reorder_and_explain_recommendations(self):
        server.save_user_context(
            {
                "active_region": "SG",
                "context": {
                    "employment_priority": "both",
                    "preferred_job_tags": ["source_official", "chinese_friendly", "conversion_possible"],
                    "muted_job_tags": ["source_jobstreet", "visa_unlikely"],
                },
            }
        )
        preferred = server.upsert_job(
            {
                "company": "Mandarin Product Lab",
                "position": "Product Operations Intern",
                "source": "Company Site / ATS",
                "url": "https://example.com/user-tag-preferred",
                "jd_text": "Singapore internship with possible full-time conversion, Mandarin support for Chinese market product operations.",
            }
        )
        muted = server.upsert_job(
            {
                "company": "Generic Marketplace",
                "position": "Product Operations Intern",
                "source": "JobStreet",
                "url": "https://sg.jobstreet.com/job/user-tag-muted",
                "jd_text": "Singapore internship. No visa sponsorship. Product operations support.",
            }
        )
        with server.get_db() as conn:
            conn.execute("update jobs set score=4.1, status='Recommended' where id in (?, ?)", (preferred["id"], muted["id"]))

        recommendations = server.list_today_recommendations({"limit": ["20"], "region": ["SG"]})["jobs"]
        preferred_ranked = next(item for item in recommendations if item["id"] == preferred["id"])
        muted_ranked = next(item for item in recommendations if item["id"] == muted["id"])

        self.assertLess(recommendations.index(preferred_ranked), recommendations.index(muted_ranked))
        self.assertGreater(preferred_ranked["user_tag_adjustment"], 0)
        self.assertLess(muted_ranked["user_tag_adjustment"], 0)
        self.assertIn("官网 / ATS", [item["label"] for item in preferred_ranked["user_tag_matches"]])
        self.assertIn("JobStreet", [item["label"] for item in muted_ranked["user_tag_mutes"]])
        self.assertIn("少看标签", muted_ranked["recommendation_reason"])

    def test_overall_rank_outweighs_small_differences_in_preferred_tag_counts(self):
        common = {
            "source": "LinkedIn",
            "status": "Recommended",
            "region": "SG",
            "city": "Singapore",
            "location": "Singapore",
            "employment_type": "Internship",
            "score": 4.0,
            "base_score": 4.0,
            "found_date": server.today(),
            "recommended_date": server.today(),
            "last_checked_at": server.now_iso(),
            "updated_at": server.now_iso(),
            "eligibility_flags": [],
            "direction_mismatch_adjustment": 0.0,
            "user_tag_mutes": [],
        }
        stronger_overall = {
            **common,
            "id": 1,
            "company": "Strong Product Co",
            "position": "Product Design Intern",
            "url": "https://example.com/strong-overall",
            "jd_text": "Singapore product design internship.",
            "rank_score": 4.8,
            "user_tag_priority": 0.12,
            "user_tag_adjustment": 0.12,
        }
        more_lightweight_tags = {
            **common,
            "id": 2,
            "company": "Tag Heavy Co",
            "position": "Marketing Intern",
            "url": "https://example.com/tag-heavy",
            "jd_text": "Singapore marketing internship.",
            "rank_score": 4.3,
            "user_tag_priority": 0.5,
            "user_tag_adjustment": 0.5,
        }

        payload = server.recommendation_payload_from_ranked_jobs(
            [more_lightweight_tags, stronger_overall],
            "SG",
            20,
            {"preferred_job_tags": ["source_linkedin"], "muted_job_tags": []},
            ["ux-product-design"],
            "user_context",
            [],
        )

        self.assertEqual([job["id"] for job in payload["jobs"]], [1, 2])

    def test_lightweight_tags_cannot_overpower_a_muted_contract_role(self):
        preference = server.user_tag_preference_for_job(
            {
                "position": "Python Developer",
                "employment_type": "Contract",
                "source": "LinkedIn",
                "found_date": server.today(),
                "jd_text": "AI product automation with UX collaboration.",
                "salary_fit": "unknown",
            },
            {
                "preferred_job_tags": ["source_linkedin", "fresh_today", "ux_related", "product_related", "ai_related"],
                "muted_job_tags": ["contract"],
            },
            "SG",
        )

        self.assertLessEqual(preference["user_tag_adjustment"], 0.35)
        self.assertIn("contract", [item["id"] for item in preference["user_tag_mutes"]])

    def test_muted_roles_sort_after_non_muted_roles_even_with_other_tag_matches(self):
        server.save_user_context(
            {
                "active_region": "SG",
                "context": {
                    "employment_priority": "both",
                    "preferred_job_tags": ["source_linkedin", "fresh_today", "ai_related", "product_related"],
                    "muted_job_tags": ["contract"],
                },
            }
        )
        contract = server.upsert_job({"company": "Contract AI Co", "position": "Python Developer", "source": "LinkedIn", "url": "https://example.com/muted-contract", "job_type": "Contract", "jd_text": "Singapore AI product automation contract role."})
        internship = server.upsert_job({"company": "Internship Co", "position": "Operations Intern", "source": "InternSG", "url": "https://example.com/non-muted-intern", "job_type": "Internship", "jd_text": "Singapore operations internship."})
        with server.get_db() as conn:
            conn.execute("update jobs set score=5.0, status='Recommended' where id=?", (contract["id"],))
            conn.execute("update jobs set score=3.0, status='Recommended' where id=?", (internship["id"],))

        recommendations = server.list_today_recommendations({"limit": ["20"], "region": ["SG"]})["jobs"]

        contract_index = next(index for index, job in enumerate(recommendations) if job["id"] == contract["id"])
        internship_index = next(index for index, job in enumerate(recommendations) if job["id"] == internship["id"])
        self.assertLess(internship_index, contract_index)

    def test_preferred_tags_change_top_recommendation_range(self):
        server.save_user_context(
            {
                "active_region": "SG",
                "context": {
                    "employment_priority": "both",
                    "preferred_job_tags": ["source_official"],
                    "muted_job_tags": [],
                },
            }
        )
        official = server.upsert_job(
            {
                "company": "Official Match Co",
                "position": "Product Intern",
                "source": "Company Site / ATS",
                "url": "https://example.com/official-match",
                "jd_text": "Singapore product internship.",
            }
        )
        for index in range(7):
            job = server.upsert_job(
                {
                    "company": f"Broad Source {index}",
                    "position": "Product Intern",
                    "source": "LinkedIn",
                    "url": f"https://example.com/broad-{index}",
                    "jd_text": "Singapore product internship.",
                }
            )
            with server.get_db() as conn:
                conn.execute("update jobs set score=4.8, status='Recommended' where id=?", (job["id"],))
        with server.get_db() as conn:
            conn.execute("update jobs set score=4.76, status='Recommended' where id=?", (official["id"],))

        payload = server.list_today_recommendations({"limit": ["5"], "region": ["SG"]})
        top_ids = [job["id"] for job in payload["jobs"]]
        official_ranked = next(item for item in payload["jobs"] if item["id"] == official["id"])

        self.assertIn(official["id"], top_ids)
        self.assertGreater(official_ranked["user_tag_priority"], 0)
        self.assertGreaterEqual(payload["tag_scope"]["matched_jobs"], 1)


class MultiRegionTests(TempAppMixin, unittest.TestCase):
    def test_default_context_does_not_preselect_fixed_directions(self):
        context = server.default_user_context()

        for region_context in context["contexts"].values():
            self.assertEqual(region_context["target_directions"], [])

    def test_resume_analysis_only_returns_evidence_backed_directions(self):
        analysis = server.build_local_resume_analysis(
            """
            Planned community content campaigns for a student club.
            Wrote social media copy, managed editorial calendar, and tracked conversion from posts to event signups.
            Improved audience segmentation for marketing experiments and documented campaign learnings.
            """
        )
        direction_ids = [item["id"] for item in analysis["directions"]]

        self.assertIn("growth-content", direction_ids)
        self.assertNotIn("ai-product", direction_ids)
        self.assertNotIn("ux-product-design", direction_ids)
        self.assertTrue(all(item["score"] > 0 for item in analysis["directions"]))

    def test_resume_analysis_beats_stale_context_directions_for_ranking(self):
        server.save_user_context({"active_region": "SG", "context": {"target_directions": ["ai-product"]}})
        server.save_uploaded_resume(
            "growth-resume.txt",
            b"Community content campaigns, copywriting, marketing experiments, conversion tracking, and audience segmentation.",
            "text/plain",
        )

        direction_ids, source = server.active_preference_direction_ids()

        self.assertEqual(source, "resume_analysis")
        self.assertEqual(direction_ids, ["growth-content"])

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
        self.assertIn("sg_internship_to_fulltime", [item["value"] for item in sg_options["career_goal_options"]])
        self.assertIn("chinese_friendly", [item["value"] for item in sg_options["language_preference_options"]])
        self.assertIn("greater_china", [item["value"] for item in sg_options["company_group_options"]])
        tag_values = [item["value"] for item in sg_options["job_tag_options"]]
        self.assertIn("conversion_possible", tag_values)
        self.assertIn("visa_possible", tag_values)
        self.assertIn("source_official", tag_values)
        self.assertIn("fresh_today", tag_values)
        self.assertIn("high_experience", tag_values)

    def test_user_context_saves_selectable_job_tags_and_filters_invalid_values(self):
        context = server.save_user_context(
            {
                "active_region": "SG",
                "context": {
                    "preferred_job_tags": ["internship", "visa_possible", "not-a-real-tag"],
                    "muted_job_tags": ["high_experience", "source_jobstreet", "also-fake"],
                },
            }
        )
        sg_context = context["contexts"]["SG"]

        self.assertEqual(sg_context["preferred_job_tags"], ["internship", "visa_possible"])
        self.assertEqual(sg_context["muted_job_tags"], ["high_experience", "source_jobstreet"])

    def test_singapore_company_catalog_has_new_radar_fields(self):
        catalog = server.company_catalog("SG")
        by_company = {item["company"]: item for item in catalog}

        for company in [
            "IKEA Singapore",
            "foodpanda Singapore",
            "POP MART Singapore",
            "Changi Airport Group",
            "PatSnap",
            "Hypotenuse AI",
            "WIZ.AI",
            "ADVANCE.AI",
            "Flowmingo AI",
            "NodeFlair",
            "Funding Societies",
            "YouTrip",
            "PropertyGuru Group",
            "EPOS",
            "Moomoo Singapore",
            "Ant International",
            "Alibaba Cloud Singapore",
            "Lark",
            "Huawei Singapore",
            "SHEIN Singapore",
            "Singtel",
        ]:
            self.assertIn(company, by_company)
            self.assertTrue(by_company[company].get("recommend_reason"))
            self.assertTrue(by_company[company].get("tags"))
            self.assertIn("matched_jobs_count", by_company[company])
            self.assertTrue(by_company[company].get("aliases"))
            self.assertTrue(by_company[company].get("company_group"))
            self.assertTrue(by_company[company].get("language_signal"))
            self.assertTrue(by_company[company].get("sponsorship_signal"))
            self.assertTrue(by_company[company].get("official_careers_url"))

        self.assertIn("中文友好概率较高", by_company["POP MART Singapore"]["tags"])
        self.assertEqual(by_company["YouTrip"]["url"], "https://apply.workable.com/youtrip/?lng=en")
        self.assertEqual(by_company["PropertyGuru Group"]["url"], "https://propertyguru.wd105.myworkdayjobs.com/PropertyGuru")

    def test_company_job_matching_uses_backend_aliases(self):
        wiz = server.upsert_job(
            {
                "region": "SG",
                "company": "WIZ HOLDINGS PTE LTD",
                "position": "AI Conversational Designer Internship",
                "source": "JobStreet",
                "url": "https://sg.jobstreet.com/job/wiz-alias",
                "jd_text": "Singapore conversational AI internship for UX writing and customer journeys.",
            }
        )
        advance = server.upsert_job(
            {
                "region": "SG",
                "company": "Advance Intelligence Group",
                "position": "Product Manager Intern",
                "source": "LinkedIn",
                "url": "https://www.linkedin.com/jobs/view/4412345678",
                "jd_text": "Singapore AI fintech product internship.",
            }
        )
        foodpanda = server.upsert_job(
            {
                "region": "SG",
                "company": "foodpanda",
                "position": "Marketing Analytics Intern",
                "source": "LinkedIn",
                "url": "https://www.linkedin.com/jobs/view/4412345679",
                "jd_text": "Singapore local services marketing analytics internship.",
            }
        )
        unrelated = server.upsert_job(
            {
                "region": "SG",
                "company": "Evo Commerce",
                "position": "Artificial Intelligence Engineer",
                "source": "LinkedIn",
                "url": "https://www.linkedin.com/jobs/view/4412345680",
                "jd_text": "The team has past experience at Grab, TikTok, Zalora, FoodPanda, and Shopee.",
            }
        )

        wiz_payload = server.company_jobs_payload("WIZ.AI", "SG")
        advance_payload = server.company_jobs_payload("ADVANCE.AI", "SG")
        foodpanda_payload = server.company_jobs_payload("foodpanda Singapore", "SG")

        self.assertIn(wiz["id"], [job["id"] for job in wiz_payload["jobs"]])
        self.assertIn(advance["id"], [job["id"] for job in advance_payload["jobs"]])
        self.assertIn(foodpanda["id"], [job["id"] for job in foodpanda_payload["jobs"]])
        self.assertNotIn(unrelated["id"], [job["id"] for job in foodpanda_payload["jobs"]])
        self.assertEqual(wiz_payload["jobs"][0]["company_match_source_label"], "JobStreet 匹配")
        catalog = {item["company"]: item for item in server.company_catalog("SG")}
        self.assertGreater(catalog["WIZ.AI"]["matched_jobs_count"], 0)
        self.assertGreater(catalog["ADVANCE.AI"]["matched_jobs_count"], 0)

    def test_dismissed_catalog_company_hides_jobs_until_refollowed(self):
        job = server.upsert_job(
            {
                "region": "SG",
                "company": "Canva",
                "position": "Design Platform Intern",
                "source": "LinkedIn",
                "url": "https://www.linkedin.com/jobs/view/canva-dismiss-test",
                "jd_text": "Singapore design platform internship for product design and UX.",
            }
        )
        with server.get_db() as conn:
            conn.execute("update jobs set score=4.5, status='Recommended' where id=?", (job["id"],))
        catalog_before = {item["company"]: item for item in server.company_catalog("SG")}
        canva = catalog_before["Canva"]
        self.assertFalse(canva.get("watched"))
        self.assertGreater(canva["matched_jobs_count"], 0)
        self.assertIn(job["id"], [item["id"] for item in server.list_today_recommendations({"region": ["SG"], "limit": ["50"]})["jobs"]])

        dismissed = server.dismiss_watch_company({**canva, "region": "SG"})
        self.assertEqual(dismissed["status"], "Dropped")
        catalog_hidden = {item["company"]: item for item in server.company_catalog("SG")}["Canva"]
        hidden_payload = server.company_jobs_payload("Canva", "SG")
        hidden_jobs = server.list_jobs_payload({"region": ["SG"]})
        hidden_job = next(item for item in hidden_jobs if item["id"] == job["id"])
        hidden_recommendations = server.list_today_recommendations({"region": ["SG"], "limit": ["50"]})["jobs"]

        self.assertTrue(catalog_hidden["dismissed"])
        self.assertEqual(catalog_hidden["matched_jobs_count"], 0)
        self.assertEqual(hidden_payload["jobs"], [])
        self.assertEqual(hidden_payload["last_scan_status"], "hidden")
        self.assertTrue(hidden_job["company_hidden_by_watchlist"])
        self.assertNotIn(job["id"], [item["id"] for item in hidden_recommendations])

        server.add_watch_company({**canva, "region": "SG", "user_added": False})
        restored_payload = server.company_jobs_payload("Canva", "SG")
        restored_recommendations = server.list_today_recommendations({"region": ["SG"], "limit": ["50"]})["jobs"]

        self.assertIn(job["id"], [item["id"] for item in restored_payload["jobs"]])
        self.assertNotIn(job["id"], [item["id"] for item in restored_recommendations])

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

    def test_active_region_filters_recommendations_and_routes_watched_company_jobs_to_company_section(self):
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
        self.assertNotIn(cn_job["id"], ids)
        self.assertNotIn(sg_job["id"], ids)
        company_payload = server.company_jobs_payload("ByteDance", "CN", "Shanghai")
        self.assertIn(cn_job["id"], [job["id"] for job in company_payload["jobs"]])
        watched_job = next(job for job in server.list_jobs_payload({"region": ["CN"], "city": ["Shanghai"]}) if job["id"] == cn_job["id"])
        self.assertTrue(watched_job["company_watched_by_user"])

    def test_supplemental_candidate_flag_excludes_watched_company_jobs(self):
        server.add_watch_company(
            {
                "region": "SG",
                "company": "WIZ.AI",
                "aliases": ["WIZ HOLDINGS PTE LTD"],
                "url": "https://www.wiz.ai/pages/join-us.html",
                "focus": "AI internships",
            }
        )
        watched_job = server.upsert_job(
            {
                "region": "SG",
                "company": "WIZ HOLDINGS PTE LTD",
                "position": "AI Product Intern",
                "source": "LinkedIn",
                "url": "https://example.com/wiz-supplemental",
                "jd_text": "Singapore AI product internship with Mandarin market work.",
            }
        )
        other_job = server.upsert_job(
            {
                "region": "SG",
                "company": "Independent Product Lab",
                "position": "Product Intern",
                "source": "InternSG",
                "url": "https://example.com/independent-supplemental",
                "jd_text": "Singapore product internship.",
            }
        )
        with server.get_db() as conn:
            conn.execute("update jobs set score=4.8, status='Recommended' where id=?", (watched_job["id"],))
            conn.execute("update jobs set score=4.2, status='Recommended' where id=?", (other_job["id"],))

        jobs = server.list_jobs_payload({"region": ["SG"], "compact": ["1"]})
        jobs_by_id = {job["id"]: job for job in jobs}

        self.assertFalse(jobs_by_id[watched_job["id"]]["supplemental_candidate"])
        self.assertTrue(jobs_by_id[other_job["id"]]["supplemental_candidate"])
        recommendations = server.list_today_recommendations({"region": ["SG"], "limit": ["20"]})
        self.assertNotIn(watched_job["id"], [job["id"] for job in recommendations["jobs"]])

    def test_supplemental_candidates_exclude_watched_source_when_company_name_is_unreliable(self):
        watched_source_job = server.upsert_job(
            {
                "region": "SG",
                "company": "Careers Portal",
                "position": "Product Intern",
                "source": "关注公司公开来源",
                "url": "https://example.com/watched-source-product-intern",
                "jd_text": "Singapore product internship.",
            }
        )
        with server.get_db() as conn:
            conn.execute(
                "update jobs set score=4.8, status='Recommended' where id=?",
                (watched_source_job["id"],),
            )

        payload = server.list_jobs_payload({"region": ["SG"], "compact": ["1"]})
        job = next(item for item in payload if item["id"] == watched_source_job["id"])

        self.assertTrue(job["company_watched_by_user"])
        self.assertFalse(job["supplemental_candidate"])

    def test_diversified_recommendations_never_backfill_watched_company_jobs(self):
        jobs = [
            {"id": 1, "company": "Independent Product Lab", "source": "InternSG"},
            {"id": 2, "company": "WIZ HOLDINGS PTE LTD", "source": "LinkedIn"},
        ]

        selected = server.diversified_workbench_recommendations(
            jobs,
            {"wiz holdings", "wiz ai"},
            limit=20,
        )

        self.assertEqual([job["id"] for job in selected], [1])

    def test_supplemental_candidates_exclude_merged_watched_company_sources(self):
        merged_job = {
            "id": 1,
            "company": "Independent Product Lab",
            "position": "Product Intern",
            "source": "LinkedIn",
            "alternate_links": [
                {
                    "id": 2,
                    "source": "关注公司公开来源",
                    "url": "https://example.com/watched-company-role",
                }
            ],
        }

        self.assertTrue(server.is_watched_company_job(merged_job, set()))
        self.assertEqual(
            server.diversified_workbench_recommendations([merged_job], set(), limit=20),
            [],
        )

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
    def test_internsg_fetches_job_details_concurrently_and_preserves_listing_order(self):
        parsed_jobs = [
            {
                "company": f"Company {index}",
                "position": f"Product Intern {index}",
                "source": "InternSG",
                "url": f"https://www.internsg.com/job/product-intern-{index}/",
                "jd_text": "Listing summary.",
            }
            for index in range(6)
        ]
        barrier = threading.Barrier(6)

        def fake_http_get(url, **_kwargs):
            if "/jobs/?" in url:
                return "listing html"
            barrier.wait(timeout=1)
            return f'<div class="isg-detail-container">Details for {url}</div>'

        with mock.patch.object(server, "http_get", side_effect=fake_http_get):
            with mock.patch.object(server, "parse_internsg_jobs_from_html", return_value=parsed_jobs):
                jobs, failures = server.fetch_internsg_jobs(6, ["product intern"])

        self.assertEqual(failures, [])
        self.assertEqual([job["position"] for job in jobs], [f"Product Intern {index}" for index in range(6)])
        self.assertTrue(all("Details for" in job["jd_text"] for job in jobs))

    def test_company_scan_processes_eight_independent_sites_concurrently(self):
        with server.get_db() as conn:
            conn.execute("update watch_companies set status='Dropped' where region='SG'")
            for index in range(8):
                conn.execute(
                    "insert into watch_companies(company, source, url, focus, region, status) values(?, ?, ?, ?, ?, ?)",
                    (f"Parallel Co {index}", "Company Site", f"https://parallel-{index}.example/", "Product internships", "SG", "Watch"),
                )

        barrier = threading.Barrier(8)

        def fake_http_get(_url, **_kwargs):
            barrier.wait(timeout=1)
            return "<html><body>Careers</body></html>"

        with mock.patch.object(server, "http_get", side_effect=fake_http_get):
            with mock.patch.object(server, "fetch_company_ats_jobs", return_value=([], [])):
                jobs, failures = server.fetch_company_site_jobs(20, "SG")

        self.assertEqual(jobs, [])
        self.assertEqual(failures, [])

    def test_linkedin_rate_limit_failures_collapse_into_one_actionable_summary(self):
        failures = server.summarize_scan_source_failures(
            "LinkedIn（含 AI 关键词）",
            [
                "LinkedIn detail 1: HTTP Error 429: Too Many Requests",
                "LinkedIn detail 2: HTTP Error 429: Too Many Requests",
                "LinkedIn ai product intern: HTTP Error 429: Too Many Requests",
            ],
            34,
        )

        self.assertEqual(len(failures), 1)
        self.assertIn("已保留 34 条列表结果", failures[0])

    def test_linkedin_rate_limit_is_nonblocking_after_base_quota_is_saved(self):
        error = "LinkedIn 限流：详情或部分关键词请求受限；已保留 24 条列表结果，本轮已停止重复请求。"

        self.assertTrue(server.is_nonblocking_scan_warning("LinkedIn（含 AI 关键词）", error, 24))
        self.assertFalse(server.is_nonblocking_scan_warning("LinkedIn（含 AI 关键词）", error, 23))
        self.assertFalse(server.is_nonblocking_scan_warning("JobStreet", error, 24))

    def test_scan_succeeds_when_linkedin_base_quota_survives_optional_rate_limit(self):
        jobs = [
            {
                "company": f"LinkedIn Co {index}",
                "position": f"Product Intern {index}",
                "source": "LinkedIn",
                "url": f"https://www.linkedin.com/jobs/view/{4450000000 + index}",
                "jd_text": "Singapore product internship with UX research.",
            }
            for index in range(server.SOURCE_LIMITS["LinkedIn"])
        ]
        fetcher = lambda _limit: (jobs, ["LinkedIn AI query: HTTP Error 429: Too Many Requests"])

        with mock.patch.object(server, "scan_source_definitions", return_value=[("LinkedIn（含 AI 关键词）", fetcher, 42)]):
            with mock.patch.object(server, "generate_report", return_value={"path": "test"}):
                result = server.scan_sources(region="SG")

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["failures"], [])
        self.assertEqual(result["scan_run"]["sources"][0]["status"], "success")

    def test_linkedin_stops_detail_requests_after_first_rate_limit_but_keeps_listings(self):
        parsed_jobs = [
            {"company": f"Company {index}", "position": "Product Intern", "source": "LinkedIn", "url": f"https://www.linkedin.com/jobs/view/{index}", "external_job_id": str(index), "jd_text": "Product internship listing summary."}
            for index in range(3)
        ]
        detail_calls = []

        def fake_http_get(url, **_kwargs):
            if "jobPosting" in url:
                detail_calls.append(url)
                raise RuntimeError("HTTP Error 429: Too Many Requests")
            return "listing html"

        with mock.patch.object(server, "http_get", side_effect=fake_http_get):
            with mock.patch.object(server, "parse_linkedin_jobs_from_html", return_value=parsed_jobs):
                jobs, failures = server.fetch_linkedin_jobs(3, ["product intern"], "SG")

        self.assertEqual(len(jobs), 3)
        self.assertEqual(len(detail_calls), 1)
        self.assertEqual(len(failures), 1)

    def test_linkedin_uses_public_job_page_when_detail_api_is_limited(self):
        parsed_jobs = [
            {
                "company": f"Company {index}",
                "position": "Product Intern",
                "source": "LinkedIn",
                "url": f"https://www.linkedin.com/jobs/view/{index}",
                "external_job_id": str(index),
                "jd_text": "Product internship listing summary.",
            }
            for index in range(3)
        ]
        public_detail = """
          <div class="show-more-less-html__markup show-more-less-html__markup--clamp-after-5">
            Singapore product internship with user research, Figma prototyping, and AI workflows.
            Potential for full-time employment after your internship. Monthly internship stipend.
          </div>
        """

        def fake_http_get(url, **_kwargs):
            if "jobPosting" in url:
                raise RuntimeError("HTTP Error 429: Too Many Requests")
            if "/jobs/view/" in url:
                return public_detail
            return "listing html"

        with mock.patch.object(server, "http_get", side_effect=fake_http_get):
            with mock.patch.object(server, "parse_linkedin_jobs_from_html", return_value=parsed_jobs):
                jobs, failures = server.fetch_linkedin_jobs(3, ["product intern"], "SG")

        self.assertEqual(failures, [])
        self.assertTrue(all("Potential for full-time employment" in job["jd_text"] for job in jobs))

    def test_company_scan_cools_down_recent_limited_sites(self):
        with server.get_db() as conn:
            conn.execute("update watch_companies set last_scan_status='limited', last_checked_at=? where region='SG'", (server.now_iso(),))

        with mock.patch.object(server, "http_get") as http_get:
            jobs, failures = server.fetch_company_site_jobs(20, "SG")

        self.assertEqual(jobs, [])
        self.assertEqual(failures, [])
        http_get.assert_not_called()

    def test_company_scan_treats_missing_child_pages_as_empty_not_failure(self):
        with server.get_db() as conn:
            conn.execute("update watch_companies set status='Dropped' where region='SG'")
            conn.execute(
                "insert into watch_companies(company, source, url, focus, region, status) values(?, ?, ?, ?, ?, ?)",
                ("Probe Co", "Company Site", "https://probe.example/", "Product internships", "SG", "Watch"),
            )

        def fake_get(url, **_kwargs):
            if url == "https://probe.example/":
                return "<html><body>Company home</body></html>"
            raise RuntimeError("HTTP Error 404: Not Found")

        with mock.patch.object(server, "http_get", side_effect=fake_get):
            with mock.patch.object(server, "fetch_company_ats_jobs", return_value=([], [])):
                jobs, failures = server.fetch_company_site_jobs(10, "SG")

        self.assertEqual(jobs, [])
        self.assertEqual(failures, [])
        with server.get_db() as conn:
            row = conn.execute("select last_scan_status from watch_companies where company='Probe Co'").fetchone()
        self.assertEqual(row["last_scan_status"], "empty")

    def test_company_scan_keeps_root_page_failure_visible(self):
        with server.get_db() as conn:
            conn.execute("update watch_companies set status='Dropped' where region='SG'")
            conn.execute(
                "insert into watch_companies(company, source, url, focus, region, status) values(?, ?, ?, ?, ?, ?)",
                ("Offline Co", "Company Site", "https://offline.example/", "Product internships", "SG", "Watch"),
            )

        with mock.patch.object(server, "http_get", side_effect=RuntimeError("connection timed out")):
            jobs, failures = server.fetch_company_site_jobs(10, "SG")

        self.assertEqual(jobs, [])
        self.assertEqual(len(failures), 1)
        self.assertIn("Offline Co", failures[0])
        with server.get_db() as conn:
            row = conn.execute("select last_scan_status from watch_companies where company='Offline Co'").fetchone()
        self.assertEqual(row["last_scan_status"], "failed")

    def test_scan_fetches_sources_in_parallel_and_propagates_user_context(self):
        barrier = threading.Barrier(8)
        seen_users = []

        def source_fetcher(label):
            def fetch(_limit):
                seen_users.append(server.request_user_id())
                barrier.wait(timeout=1)
                return ([{"company": f"{label} Co", "position": "Product Intern", "source": label, "url": f"https://example.com/{label}", "jd_text": "Singapore product internship."}], [])
            return fetch

        definitions = [
            (f"Parallel {index}", source_fetcher(f"parallel-{index}"), 1)
            for index in range(8)
        ]
        with server.request_user_context("parallel-user"):
            server.setup_db()
            with mock.patch.object(server, "scan_source_definitions", return_value=definitions):
                result = server.scan_sources(region="SG")

        self.assertEqual(seen_users, ["parallel-user"] * 8)
        self.assertEqual(result["saved"], 8)
        self.assertEqual(result["failures"], [])

    def test_indeed_fetch_uses_browser_fallback_after_direct_403(self):
        fallback_job = {
            "company": "NLB National Library Board",
            "position": "Engagement and UX Intern",
            "source": "Indeed",
            "url": "https://sg.indeed.com/viewjob?jk=78ff7ee6054aa274",
            "location": "Hybrid work in Singapore",
            "jd_text": "Support UX research.",
        }

        with (
            mock.patch.object(server, "http_get", side_effect=RuntimeError("HTTP Error 403: Forbidden")),
            mock.patch.object(server, "fetch_indeed_jobs_with_browser", return_value=([fallback_job], [])) as browser_mock,
            mock.patch.object(server, "fetch_indeed_jobs_via_google_jobs") as serpapi_mock,
        ):
            jobs, failures = server.fetch_indeed_jobs(2, ["ux research intern"], "SG", failure_limit=1)

        self.assertEqual(jobs, [fallback_job])
        self.assertEqual(failures, [])
        browser_mock.assert_called_once()
        serpapi_mock.assert_not_called()

    def test_jobstreet_fetch_uses_public_search_api(self):
        payload = json.dumps(
            {
                "data": [
                    {
                        "id": "92606186",
                        "title": "AI Intern",
                        "companyName": "Skite Social",
                        "locations": [{"label": "Central Region"}],
                        "workTypes": ["Full time"],
                        "teaser": "Hands-on exposure to AI in real business operations.",
                    }
                ]
            }
        )
        calls = []

        def fake_http_get(url, timeout=25, retries=1):
            calls.append(url)
            self.assertIn("/api/jobsearch/v5/search", url)
            return payload

        with mock.patch.object(server, "http_get", side_effect=fake_http_get):
            jobs, failures = server.fetch_jobstreet_jobs(1, ["ai internship"], "SG")

        self.assertFalse(failures)
        self.assertEqual(jobs[0]["source"], "JobStreet")
        self.assertEqual(jobs[0]["url"], "https://sg.jobstreet.com/job/92606186")
        self.assertEqual(len(calls), 1)

    def test_scan_sources_merge_ai_queries_without_ai_visual_rows(self):
        sources = server.expected_scan_sources("SG")
        self.assertIn("LinkedIn（含 AI 关键词）", sources)
        self.assertIn("InternSG（含 AI 关键词）", sources)
        self.assertIn("Cultjobs", sources)
        self.assertIn("MyCareersFuture", sources)
        self.assertIn("Careers@Gov", sources)
        self.assertIn("Internship.sg", sources)
        self.assertIn("创业与 AI 机会", sources)
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
        self.assertEqual(details["MyCareersFuture"], "supplemental")
        self.assertEqual(details["Careers@Gov"], "primary")
        self.assertEqual(details["Internship.sg"], "supplemental")
        self.assertEqual(details["Cultjobs"], "primary")
        self.assertEqual(details["Indeed"], "supplemental")
        self.assertEqual(details["JobStreet"], "supplemental")
        self.assertEqual(details["创业与 AI 机会"], "supplemental")
        self.assertEqual(details["公司官网"], "company")

    def test_scan_overview_merges_legacy_startup_source_name(self):
        overview = server.scan_overview(
            {
                "expected_source_details": [{"source": "创业与 AI 机会", "mode": "supplemental"}],
                "run": {
                    "status": "partial",
                    "sources": [{"source": "Glints / NodeFlair / Startups", "status": "failed", "failure_count": 6}],
                    "failures_json": [],
                },
            }
        )

        self.assertEqual(len(overview["sources"]), 1)
        self.assertEqual(overview["sources"][0]["source"], "创业与 AI 机会")
        self.assertEqual(overview["sources"][0]["failure_count"], 6)

    def test_scan_overview_keeps_active_mycareersfuture_status(self):
        overview = server.scan_overview(
            {
                "expected_source_details": [
                    {"source": "Cultjobs", "mode": "primary"},
                    {"source": "MyCareersFuture", "mode": "supplemental"},
                ],
                "run": {
                    "status": "partial",
                    "sources": [
                        {"source": "Cultjobs", "status": "success", "saved_count": 4},
                        {"source": "MyCareersFuture", "status": "failed", "failure_count": 2},
                    ],
                    "failures_json": [],
                },
            }
        )

        self.assertEqual([source["source"] for source in overview["sources"]], ["Cultjobs", "MyCareersFuture"])

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

    def test_scan_reports_new_updated_and_duplicate_counts(self):
        existing = server.upsert_job(
            {
                "company": "Existing Scan Co",
                "position": "UX Intern",
                "source": "LinkedIn",
                "url": "https://www.linkedin.com/jobs/view/4440000100",
                "jd_text": "Existing Singapore UX internship.",
            }
        )

        def fixture_source(limit):
            new_job = {
                "company": "New Scan Co",
                "position": "AI Product Intern",
                "source": "InternSG",
                "url": "https://www.internsg.com/job/new-scan-quality/",
                "jd_text": "Singapore AI product internship.",
            }
            return [
                new_job,
                dict(new_job),
                {
                    "company": "Existing Scan Co",
                    "position": "UX Intern",
                    "source": "LinkedIn",
                    "url": existing["url"],
                    "jd_text": "Updated Singapore UX internship.",
                },
            ], []

        with (
            mock.patch.object(server, "scan_source_definitions", return_value=[("Fixture", fixture_source, 10)]),
            mock.patch.object(server, "generate_report"),
            mock.patch.object(server, "list_ai_jobs", return_value=[]),
        ):
            result = server.scan_sources(region="SG")

        self.assertEqual(result["scanned"], 3)
        self.assertEqual(result["saved"], 2)
        self.assertEqual(result["new"], 1)
        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["duplicates"], 1)
        self.assertEqual(result["scan_run"]["new_count"], 1)
        self.assertEqual(result["scan_run"]["updated_count"], 1)
        self.assertEqual(result["scan_run"]["duplicate_count"], 1)
        source_run = result["scan_run"]["sources"][0]
        self.assertEqual(source_run["new_count"], 1)
        self.assertEqual(source_run["updated_count"], 1)
        self.assertEqual(source_run["duplicate_count"], 1)

    def test_rescan_promotes_new_jobs_without_overwriting_user_decisions(self):
        url = "https://example.com/rescored-role"
        job = server.upsert_job(
            {
                "company": "Rescore Co",
                "position": "Operations Assistant",
                "source": "Company Site / ATS",
                "url": url,
                "jd_text": "Singapore administrative role.",
            }
        )
        self.assertEqual(job["status"], "New")

        promoted = server.upsert_job(
            {
                "company": "Rescore Co",
                "position": "AI Product Design Intern",
                "source": "Company Site / ATS",
                "url": url,
                "jd_text": "Singapore AI product design internship with UX research, service design and Figma prototyping.",
            }
        )
        self.assertEqual(promoted["status"], "Recommended")
        self.assertEqual(promoted["recommended_date"], server.today())

        with server.get_db() as conn:
            conn.execute("update jobs set status='Apply Queue' where id=?", (promoted["id"],))
        rescanned = server.upsert_job(
            {
                "company": "Rescore Co",
                "position": "AI Product Design Intern",
                "source": "Company Site / ATS",
                "url": url,
                "jd_text": "Singapore AI product design internship with UX research, service design and Figma prototyping.",
            }
        )
        self.assertEqual(rescanned["status"], "Apply Queue")

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
            thread = server.SCAN_THREADS.get(server.scan_thread_key(run_id))
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
            thread = server.SCAN_THREADS.get(server.scan_thread_key(started["run"]["id"]))
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

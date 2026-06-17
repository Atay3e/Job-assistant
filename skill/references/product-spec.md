# 求职助手 Product Spec

## Purpose

Build a daily job-search command center that helps a user find, evaluate, draft for, apply to, and track roles across their active region.

The system should optimize for consistent high-quality applications, not blind full automation. The user remains in control of final submissions.

## Components

1. Daily Scout
   - Scans regional job boards and selected company career pages.
   - Normalizes jobs into a shared schema.
   - Deduplicates against local records.

2. Match Engine
   - Reads the user's resume/profile.
   - Scores each role on a 5.0 scale.
   - Flags local eligibility restrictions such as citizen-only, PR-only, local-only, or clearance-only.
   - Promotes roles above 3.0/5.0 for resume and cover letter drafting.

3. Career Fit
   - Parses uploaded resumes locally.
   - Suggests target directions and visible evidence.
   - Lets the user select preferred directions that influence ranking.

4. Company Radar
   - Provides regional recommended company catalogs.
   - Lets users add custom career-page URLs.
   - Tracks last scan status and failures.

5. Apply Console
   - Shows the daily recommendation checklist.
   - Allows Apply, Watch, and Drop.
   - Moves user-approved roles into an application queue.

6. Tracker
   - Maintains a local database as the source of truth.
   - Preserves URLs, JD text, dates, statuses, and generated file paths.

7. Daily Report
   - Groups roles by scan date, application date, and region.
   - Reports recommended count, apply queue count, applied count, watch count, drop count, failures, and follow-ups.

## MVP Scope

Phase 1:
- Local database schema.
- Multi-region user context.
- Manual and semi-automated import from job URLs and job boards.
- Company radar.
- Daily checklist web UI.
- Resume and cover-letter draft generation for scored roles.
- Daily Markdown report.

Phase 2:
- More robust scraping connectors.
- Better company career page monitors.
- Semi-automated application form assistance.
- Follow-up reminders and interview pipeline tracking.

Phase 3:
- Selective automated submission only for low-risk forms after explicit user approval.
- Analytics on response rates and source quality.

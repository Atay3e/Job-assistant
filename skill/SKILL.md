---
name: job-assistant
description: Use when designing, building, or running the local-first Job Assistant: multi-region job scans, resume-based matching, work-authorisation filtering, top daily recommendations, human-approved applications, tailored resume and cover letter drafts, and local tracking with persistent job URLs and JD records.
---

# 求职助手

This skill governs the local-first Job Assistant workflow. Treat it as the operating contract for both automation and the local web app.

## Core Defaults

- Regions: support Singapore, China Mainland, and Hong Kong first.
- Role types: all acceptable; prioritize the user's selected job types.
- Eligibility: reject or flag hard local eligibility restrictions such as citizen-only, PR-only, local-only, clearance-only, or clearly incompatible requirements.
- Daily recommendations: show the best matched roles for the active user context.
- Submission rule: do not submit an application without explicit user confirmation.
- URL rule: preserve every original job URL permanently in local storage.
- Repeat rule: jobs marked Applied or Dropped must not appear again in future recommendations.

## Load References As Needed

- `references/product-spec.md` for architecture, daily workflow, and MVP scope.
- `references/scoring-rubric.md` for the 5.0 matching rubric.
- `references/tracker-schema.md` for local and Notion data fields.
- `references/ui-brief.md` for the local web app design direction.

## Modes

- `setup`: collect resume/profile paths, target region, work authorisation, target sources, company watchlist, and schedule.
- `scan`: collect new jobs from job boards and company career pages.
- `score`: score jobs against the user's resume/profile and eligibility filters.
- `review`: produce the daily recommendation checklist with Apply, Watch, and Drop actions.
- `draft`: create tailored resume and cover letter drafts for roles scoring above 3.0/5.0.
- `apply-queue`: prepare human-approved applications for the day.
- `tracker`: update local database, local web UI, and optional Notion master table.
- `report`: produce the daily summary with counts, links, outcomes, and blockers.
- `company-watch`: monitor selected companies and custom career-page URLs.

## Daily Contract

1. Load the active user context.
2. Scan configured regional sources and company career pages.
3. Normalize each job into a canonical record.
4. Deduplicate by URL, company, role title, and external job id when available.
5. Exclude Applied and Dropped jobs from new recommendations.
6. Apply hard eligibility filters and flag uncertain cases.
7. Score each remaining job on the 5.0 rubric.
8. Rank with user preference, region, location, and watched-company signals.
9. For roles above 3.0, draft tailored resume and cover letter material.
10. Move user-approved roles into the application queue.
11. Record every decision and URL locally.
12. Generate a daily report grouped by date and active region.

## Safety And Integrity

- Respect platform limits and anti-bot behavior.
- Prefer human-in-the-loop application flows when forms, captchas, login walls, or custom questions appear.
- Never invent facts for application questions.
- Draft answers only from the user's evidence, resume, or explicit chat input.
- For employer-specific questions, create answer drafts and mark anything that needs user confirmation.
- Keep job descriptions, URLs, dates, generated files, and decision history traceable.

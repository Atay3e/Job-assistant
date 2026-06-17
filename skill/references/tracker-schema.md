# Tracker Schema

The local database is the source of truth. Notion is the master review table and must remain synced.

## Required Notion Fields

The Notion master table must include these exact fields:

- `Name`: title. Recommended format: company plus role.
- `Status`: status or select. Example values below.
- `URL`: url. Always preserve the original job page URL.
- `position`: rich text or text. Exact job title.
- `JD`: rich text, long text, or page body. Store the full job description or a durable excerpt plus local JD path.

## Strongly Recommended Notion Fields

- `Company`: text.
- `Source`: select, e.g. LinkedIn, Indeed, InternSG, Company Site.
- `Score`: number.
- `Batch Date`: date. The daily recommendation batch date.
- `Found Date`: date.
- `Recommended Date`: date.
- `Applied Date`: date.
- `Decision`: select, e.g. Apply, Watch, Drop.
- `Eligibility Flags`: multi-select.
- `Resume Path`: text or url.
- `Cover Letter Path`: text or url.
- `Notes`: rich text.
- `Drop Reason`: text.
- `Last Checked`: date.

## Status Values

- `New`
- `Recommended`
- `Apply Queue`
- `Drafted`
- `Applied`
- `Watch`
- `Dropped`
- `Follow Up`
- `Interview`
- `Rejected`
- `Offer`
- `Closed`

## Local Tables

### jobs

- `id`
- `company`
- `position`
- `name`
- `source`
- `url`
- `external_job_id`
- `location`
- `job_type`
- `jd_text`
- `jd_hash`
- `score`
- `status`
- `decision`
- `eligibility_flags`
- `found_date`
- `batch_date`
- `recommended_date`
- `applied_date`
- `last_checked_at`
- `notion_page_id`

### applications

- `id`
- `job_id`
- `status`
- `resume_path`
- `cover_letter_path`
- `submitted_at`
- `submission_mode`
- `custom_questions_json`
- `notes`

### daily_reports

- `date`
- `searched_count`
- `recommended_count`
- `drafted_count`
- `apply_queue_count`
- `applied_count`
- `watch_count`
- `drop_count`
- `failures_json`
- `report_markdown_path`

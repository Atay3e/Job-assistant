# Local Web App UI Brief

Use the frontend design skills when building the local web app. The app should feel like a focused job-search operations desk, not a landing page.

## Product Feel

- Quiet, premium, and highly usable.
- Dashboard-like, but not cluttered.
- Built for daily repeated use: scan, compare, decide, apply, record.
- Avoid marketing hero sections, oversized decorative cards, or generic AI gradients.
- Use icons for actions where appropriate, with tooltips for unfamiliar controls.

## Main Views

1. Today
   - Daily top-20 checklist.
   - Apply, Watch, Drop controls.
   - Score, source, eligibility flags, and short match rationale.
   - Clear date grouping.

2. Job Detail
   - Original URL.
   - JD.
   - Match breakdown.
   - Eligibility flags.
   - Tailored resume and cover letter draft links.
   - Custom question draft area.

3. Apply Queue
   - Up to 15 roles for the day.
   - Submission readiness state.
   - Manual confirmation before final submit.

4. Tracker
   - Full table across all dates.
   - Filters by date, status, source, company, score, and decision.
   - Applied and Dropped jobs remain visible but do not re-enter recommendations.

5. Company Watch
   - Watched company list.
   - New roles by company.
   - Last checked time and source URL.

6. Reports
   - Daily summary.
   - Application counts and failure reasons.
   - Links to generated Markdown reports.

## Visual Direction

- Use a restrained neutral base with one clear accent color.
- Use stable table dimensions and responsive constraints.
- Prefer compact, readable information layouts over large decorative panels.
- Numbers and scores should be easy to scan.
- Long URLs and job titles must wrap cleanly without breaking layout.
- Include empty, loading, and error states.
- Mobile should become a single-column decision queue.

## Key Interaction

The primary daily workflow is:

`Scan -> Review Top 20 -> Apply/Watch/Drop -> Draft -> Confirm Submit -> Track -> Report`

The interface should keep this flow visible without explaining it with instructional marketing copy.

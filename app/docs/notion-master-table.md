# Notion Master Table

Create one Notion database for the job search master tracker. The local app keeps the durable database; Notion is the readable master table.

## Required Fields

| Field | Type | Notes |
| --- | --- | --- |
| Name | Title | Company plus role. |
| Status | Status or Select | New, Recommended, Apply Queue, Drafted, Applied, Watch, Dropped, Follow Up, Interview, Rejected, Offer, Closed. |
| URL | URL | Original job page URL. This is mandatory and must never be removed. |
| position | Text or Rich Text | Exact job title. |
| JD | Rich Text or Page Body | Full job description, or durable excerpt plus local JD path. |

## Recommended Fields

| Field | Type |
| --- | --- |
| Company | Text |
| Source | Select |
| Score | Number |
| Batch Date | Date |
| Found Date | Date |
| Recommended Date | Date |
| Applied Date | Date |
| Decision | Select |
| Eligibility Flags | Multi-select |
| Resume Path | Text |
| Cover Letter Path | Text |
| Notes | Rich Text |
| Drop Reason | Text |
| Last Checked | Date |

## Date Rule

Use `Batch Date` for the daily recommendation batch and `Applied Date` for actual submissions. This keeps May 10, May 11, and later batches cleanly separated.

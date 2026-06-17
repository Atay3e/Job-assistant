# Matching Rubric

Score each job from 0.0 to 5.0. Recommend the top 20 jobs each day. Generate tailored resume and cover letter drafts for jobs above 3.0.

## Rubric

1. Role fit, 0.0 to 1.0
   - 1.0: clearly fits the user's broad target space.
   - 0.5: adjacent role with transferable evidence.
   - 0.0: unrelated role.

2. Seniority and job type fit, 0.0 to 1.0
   - 1.0: internship, graduate, entry-level, junior, or suitable full-time.
   - 0.5: slightly above level but plausible.
   - 0.0: clearly senior, manager, or requires extensive experience.

3. Region and eligibility fit, 0.0 to 1.0
   - 1.0: matches the active region/city and no hard local-only restriction detected.
   - 0.5: matches the active region but work authorisation or sponsorship is unclear.
   - 0.0: requires a clearly incompatible citizenship, PR, local-only, clearance-only, or work-authorisation status.

4. Evidence fit, 0.0 to 1.0
   - 1.0: the user's resume has strong evidence for the JD requirements.
   - 0.5: some evidence exists but tailoring is needed.
   - 0.0: little or no evidence.

5. Strategic value, 0.0 to 1.0
   - 1.0: strong company, relevant domain, growth potential, or preferred market signal.
   - 0.5: acceptable but not high-priority.
   - 0.0: weak signal or low value.

## Flags

Always record flags separately from the score:
- `citizen_or_pr_only`
- `local_only`
- `clearance_required`
- `experience_too_high`
- `visa_unclear`
- `custom_questions`
- `captcha_or_login_wall`
- `duplicate`
- `already_applied`
- `dropped_before`

## Recommendation Rules

- Jobs with score below 3.0 can be stored but should not enter the top-20 recommendation list unless the user asks to inspect low-confidence roles.
- Jobs above 3.0 should receive resume and cover letter drafts.
- Jobs with hard eligibility conflicts should not be recommended even if other dimensions score well.
- Jobs marked Applied or Dropped must not be recommended again.

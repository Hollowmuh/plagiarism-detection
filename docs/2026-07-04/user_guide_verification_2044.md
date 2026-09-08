# Plan: User Guide + Feature Verification

## Goal
Write a detailed, accurate user guide covering every feature of the system (student/teacher/admin/API perspectives), and verify each documented feature actually works via live testing against the deployed VM before writing it down as fact.

## Scope of features to verify

**Detection pipeline (backend API)**
- Submit document (PDF/DOCX/TXT) → 202 Accepted
- Status polling (pending/extracting/detecting/completed/failed)
- Full submission details
- Detection results (scores, tier resolved, matched passages, AI-detection)
- Submission deletion (+ index purge, verified earlier today)
- Health check
- File-type/size validation (reject unsupported types, oversized files)
- Auth (Bearer token required, rejects missing/invalid key)

**Moodle plugin (student-facing)**
- File submission auto-capture (observer → ad-hoc task)
- Online text submission auto-capture
- Student disclosure notice
- Similarity badge on own submission (color-coded)
- AI-detection badge (separate, advisory)

**Moodle plugin (teacher-facing)**
- Similarity badge on grading page
- Report page (score breakdown, matched passages, AI section)
- Cross-course access control (today's IDOR fix)
- Per-module enable/disable
- Global plugin enable/disable + API connection settings

**Operational**
- Fast result delivery (poll_result, ~15-20s typical)
- Fallback scheduled polling (check_results, safety net)
- Dedup (today's fix — resubmitting identical content doesn't create duplicates)
- Cost model / escalation behavior (tau_low/tau_high gating)

## Method
For each feature: either cite already-verified evidence from this session (with source), or run a fresh, targeted live test against the deployed VM (`plagiarism-detector-vm`). Do not document a feature as "working" without one or the other.

## Output
`docs/USER_GUIDE.md` — durable reference doc, not dated (unlike this plan), covering setup, all four user roles' workflows, the API reference, configuration, and troubleshooting.

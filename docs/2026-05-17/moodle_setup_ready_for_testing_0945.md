# Moodle + DualTier — Ready for Testing

**Date:** 2026-05-17
**State:** All backend bugs fixed, Moodle configured, test data created. Ready for end-to-end UI testing.

---

## Quick start — test plan

1. Open http://localhost:8080
2. Log in as **teacher1 / Teacher123!**
3. Open the course **Plagiarism Test Course** → **Test Plagiarism Assignment**
4. Log out
5. Log in as **student1 / Student123!**
6. Open the assignment, click *Add submission*, upload a `.txt` file with the content from "Source document" below.
7. Submit.
8. Log out → log in as **student2 / Student123!**
9. Upload a `.txt` file with the content from "Plagiarism copy" below.
10. Log out → log in as **student3 / Student123!**
11. Upload a `.txt` file with content from "Clean document" below.
12. Log out → log in as **teacher1**
13. Open the assignment → *View all submissions*.
14. **Expected:** Each student row shows a colored badge:
    - student1: **green** (~0%, original)
    - student2: **red** (~77%, tier1)
    - student3: **green** (~0%, original)
15. Click student2's badge → opens **report.php** showing the match against student1's submission.

**Important:** the dualtier plugin polls the backend every 5 minutes via `check_results` scheduled task. To force an immediate refresh, run:
```powershell
docker exec plagiarism-detection-moodle-1 sh -c "cd /usr/src/moodle && php admin/cli/scheduled_task.php --execute='\plagiarism_dualtier\task\check_results'"
```

---

## Service URLs

| Service | URL | Notes |
|---|---|---|
| Moodle | http://localhost:8080 | Web UI |
| Plagiarism API | http://localhost:8000 | Backend; from Moodle container use `http://api:8000` |
| API docs (Swagger) | http://localhost:8000/docs | |
| Flower (Celery) | http://localhost:5555 | Task monitoring |

## Credentials

| Role | Username | Password |
|---|---|---|
| Site admin | admin | Admin123! |
| Teacher | teacher1 | Teacher123! |
| Student | student1 | Student123! |
| Student | student2 | Student123! |
| Student | student3 | Student123! |

## Test data IDs (Moodle DB)

- Course: `id=2, shortname=PLAG101`
- Assignment: `cmid=4, assignid=1, name='Test Plagiarism Assignment'`
- Plugin config: `mdl_plagiarism_dualtier_config row for cmid=4 → enabled=1`

## Plugin configuration (`mdl_config_plugins`)

```
plagiarism_dualtier/enabled = 1
plagiarism_dualtier/apiurl  = http://api:8000/api/v1
plagiarism_dualtier/apikey  = dev-secret-key-change-in-production
plagiarism_dualtier/version = 2026051500
```

Core: `mdl_config: enableplagiarism = 1`.

---

## Test documents (paste into .txt files)

### Source document (student1)
```
The mitochondrion is a double-membrane-bound organelle found in most eukaryotic cells.
Mitochondria generate most of a cell's supply of adenosine triphosphate.
Cellular respiration occurs inside the mitochondria where glucose is broken down into ATP.
The inner membrane is folded into cristae which increase surface area for ATP production.
Mitochondria are often called the powerhouses of the cell.
Damage to mitochondria is an important factor in human diseases.
```

### Plagiarism copy (student2 — should flag red ~77%)
```
The mitochondrion is a double-membrane-bound organelle found in most eukaryotic cells.
Mitochondria generate most of a cell's supply of adenosine triphosphate.
These tiny powerhouses are crucial for life as we know it on Earth today.
Cellular respiration occurs inside the mitochondria where glucose is broken down into ATP.
Mitochondria are often called the powerhouses of the cell.
```

### Clean document (student3 — should stay green ~0%)
```
The Eiffel Tower is a wrought-iron lattice tower in Paris, France.
It was constructed from 1887 to 1889 for the World's Fair.
The tower is 330 metres tall and weighs 10,100 tonnes.
```

---

## Bugs fixed this session

### Bug 1 — Worker stale DB transaction during first-time model load (P1)
**Fix:** Added `@worker_ready.connect` signal in [backend/app/tasks/celery_app.py](../../backend/app/tasks/celery_app.py) that calls `get_tier1_detector()` + `get_tier2_detector()` at worker startup. Model now loads before any tasks run.

### Bug 2 — Tier-1 matches not persisted to SimilarityPair (P1)
**Fix:** In [backend/app/tasks/detection_tasks.py](../../backend/app/tasks/detection_tasks.py):
- Changed index key from `str(sub.id)` (submission_id) → `str(documents[0].id)` (document_id) so detection and indexing share the same key.
- After detection commits the result, look up the source `Document` from `best_match_id` and insert a `SimilarityPair` row.
- `match_type = "tier2" if escalated else "tier1"`.

### Bug 3 — `--reload --workers 2` in production compose (P2)
**Fix:** Removed `--reload` from `api` command in [docker-compose.yml](../../docker-compose.yml).

### Bug 4 — API race: task queued before DB commit (P1 — discovered during re-verification)
**Symptom:** Second submission sometimes stayed `pending` forever — worker dequeued the task before the API committed the row, hit `submission_not_found`, dropped silently.
**Fix:** In [backend/app/api/v1/submissions.py](../../backend/app/api/v1/submissions.py) `create_submission`: explicit `await db.commit()` BEFORE `extract_text.delay(...)`. A second `await db.commit()` after sets `celery_task_id`.

### Verification (post-fix, end-to-end)
| Doc | tier1 | plagiarised | matches array | E2E time |
|---|---|---|---|---|
| source (empty corpus) | 0.0 | False | `[]` | 5.2 s |
| copy (heavy overlap) | 0.77 | True | `[{source_document_id, score=0.77, type=tier1}]` | < 5 s |
| clean (unrelated) | 0.0 | False | `[]` | **2.4 s** (was indefinite hang) |

---

## Plugin findings (non-blocking, FYI)

- The plugin uses `plagiarism_plugin::save_form_elements()` which is **deprecated** in Moodle 4+. Newer API is `plagiarism_dualtier_coursemodule_edit_post_actions()`. Migration not required for testing but should be done before any Moodle 5 upgrade.
- The plugin's admin URL config default is `http://localhost:8000/api/v1` — correct for host access, but inside the moodle container it needs `http://api:8000/api/v1`. Already set to the container-internal value in this environment.

---

## Re-running the test data setup (idempotent)

Script: [moodle-plugin/setup_test_data.php](../../moodle-plugin/setup_test_data.php). Re-run with:
```powershell
docker cp "C:\Users\olomu\onedrive\documents\koloxo\ai92\plagiarism-detection\moodle-plugin\setup_test_data.php" plagiarism-detection-moodle-1:/usr/src/moodle/setup_test_data.php
docker exec plagiarism-detection-moodle-1 sh -c "cd /usr/src/moodle && php setup_test_data.php"
```
Detects existing rows and skips them.

## Re-running the backend detector verification

Script: [verify_detector_v2.py](../../verify_detector_v2.py). Run from host:
```powershell
Set-Location "C:\Users\olomu\onedrive\documents\koloxo\ai92\plagiarism-detection"
python verify_detector_v2.py
```

---

## Open items / next session

- [ ] Manual UI test (per "Quick start" above) — user is running this.
- [ ] Migrate plugin from `save_form_elements` to `plagiarism_*_coursemodule_edit_post_actions` for Moodle 4+ compliance.
- [ ] Tier-2 verification: craft a paraphrased (semantically similar but lexically distinct) document to confirm sentence-transformers + FAISS path fires and `escalated=true`.
- [ ] FAISS index already has `ntotal=900` vectors from earlier runs — consider clearing `/data/faiss/index.faiss` before clean tests to avoid surprise tier-2 hits.
- [ ] Production hardening: real API key, separate DB, model bake-into-image to skip first-run download.

# Full Stack Bring-up — 2026-05-17

## Status
All services up and healthy.

| Service | Container | Endpoint | Status |
|---|---|---|---|
| Backend API | `plagiarism-detection-api-1` | http://localhost:8000 | healthy |
| Celery worker | `plagiarism-detection-celery-worker-1` | — | up (1 worker registered) |
| Celery beat | `plagiarism-detection-celery-beat-1` | — | up |
| Flower | `plagiarism-detection-flower-1` | http://localhost:5555 | up |
| Postgres (app) | `plagiarism-detection-postgres-1` | localhost:5438 | healthy |
| Redis | `plagiarism-detection-redis-1` | localhost:6385 | healthy |
| Moodle | `plagiarism-detection-moodle-1` (php-fpm) + `-moodle-nginx-1` | http://localhost:8080 | up, redirecting (initial setup) |
| Moodle Postgres | `plagiarism-detection-moodle-db-1` | — | healthy |

## Verification commands run

```powershell
# Backend
python -c "import requests; print(requests.get('http://localhost:8000/api/v1/health').json())"
# → {"status":"healthy","database":"ok","redis":"ok","workers":"ok (1 workers)"}

python -c "import requests; print(requests.get('http://localhost:8000/api/v1/health/ready').json())"
# → {"status":"ready"}

# Moodle
python -c "import requests; r=requests.get('http://localhost:8080/', allow_redirects=False); print(r.status_code, r.headers.get('X-Powered-By'))"
# → 303 PHP/7.3.29 (Moodle redirect, expected)

# Plugin mounted in Moodle container
docker exec plagiarism-detection-moodle-1 ls /usr/src/moodle/plagiarism/dualtier
# → amd, classes, db, lang, lib.php, pix, report.php, settings.php, styles.css, version.php
```

## Issues encountered & resolution

### 1. moodle-db healthcheck "unhealthy" on first `compose up`
**Symptom:** `compose up -d` failed with `dependency failed to start: container plagiarism-detection-moodle-db-1 is unhealthy`.

**Root cause:** Moodle's Postgres was recovering from a dirty shutdown (May 15 crash). Recovery fsync took ~80 s, but the healthcheck's `start_period` was too short.

**Fix:** Re-run `docker compose up -d` once recovery finished — all dependents started cleanly the second time. **No code change needed**; the recovery is one-off.

**Optional follow-up:** Add `start_period: 90s` to the `moodle-db` healthcheck so future cold starts don't trip this.

### 2. Port 8000 briefly served wrong app (`agentflow`)
**Symptom:** During first bring-up, `GET http://localhost:8000/` returned `{"name":"agentflow","version":"0.1.0"}` — not the plagiarism API.

**Root cause:** Another project's container (from `C:\Users\olomu\OneDrive\Documents\Abdul\agentflow`) was holding port 8000 from an earlier session. Compose was waiting to swap it; the response we saw was the old container, not `plagiarism-detection-api-1`.

**Fix:** Self-resolved once the API container fully started. After Docker Desktop restart and clean re-bring-up, `:8000` correctly serves the Plagiarism Detection API.

### 3. Docker Desktop disconnected mid-session
**Symptom:** `npipe:////./pipe/dockerDesktopLinuxEngine` not found; all containers exited with code 255.

**Fix:** User manually restarted Docker Desktop. Stack came up clean on retry.

## Detector verification (run after stack came up)

Submitted 3 documents to confirm the detection pipeline actually works:

| Document | Content | tier1_score | is_plagiarised | Processing |
|---|---|---|---|---|
| source.txt | Mitochondria reference text (10 sentences) | 0.0 | False | 9 s (empty corpus) |
| copy.txt | Heavy verbatim copy of 6 source sentences | **0.8032** | **True** | 23 ms |
| clean2.txt | Eiffel Tower (unrelated to source) | 0.0 | False | 8 ms |

**Detector logic is correct.** Tier-1 (BM25 + winnowing) cleanly separates plagiarism from clean content. From worker logs:

```
tier1_result best_match=<source_id> bm25=0.0692 c1=0.8032 winnow=0.8032 corpus_size=1
pipeline_resolved_tier1 decision=plagiarised score=0.8031914893617021
```

Verification script: [verify_detector.py](../../verify_detector.py)

## Known bugs found during verification

### Bug 1 — Worker holds stale DB transaction across first-time model load (P1)
**Symptom:** Second submission after a fresh worker start fails with `submission_not_found` for ~8 minutes; third submission stays `pending` indefinitely.

**Root cause:** First task triggers Hugging Face download for `all-MiniLM-L6-v2` (~400 MB). During the ~8 min download, the worker's DB session holds an open transaction. When the queue resumes, the worker's snapshot predates rows committed by the API after the worker started.

**Worker log evidence:**
```
[08:01:19] Warning: You are sending unauthenticated requests to the HF Hub
[08:08:01] model_loaded model=all-MiniLM-L6-v2     ← ~7 min after task arrived
[08:08:33] submission_not_found submission_id=f07bf5bc...   ← API row exists, worker can't see it
```

**Workaround:** Restart the worker after first submission completes (`docker restart plagiarism-detection-celery-worker-1`). Then subsequent submissions work in ms.

**Fix needed in [backend/app/tasks/](../../backend/app/tasks/):** ensure model loading happens outside any DB transaction OR use a fresh session per task (`expire_on_commit=True` or create the session inside the task, not at module level).

### Bug 2 — Tier-1 matches not persisted to SimilarityPair (P2)
**Symptom:** `tier1_score=0.8032, is_plagiarised=True, matches=[]`. The `best_match` document ID is logged but never written to the result.

**Impact:** Moodle UI can show the score for Tier-1 detections but cannot link to the matched source document. Tier-2 results presumably do populate matches (not verified — would need a document that triggers escalation).

**Fix needed in [backend/app/tasks/detection_tasks.py](../../backend/app/tasks/detection_tasks.py)** (tier1_detect task): after computing `best_match`, write a SimilarityPair row before returning.

### Bug 3 — docker-compose.yml uses `--reload --workers 2` together (P2)
File: [docker-compose.yml](../../docker-compose.yml) line 48
```yaml
command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2 --reload
```
`--reload` reloads on file changes and `--workers 2` spawns 2 uvicorn workers. Together they create unstable processes on Windows Docker volume mounts (same hot-reload-loop issue Module-F hit). Drop `--reload` in the non-dev compose file.

## Next steps

- [ ] **Fix Bug 1** (stale transaction) — highest priority, makes second submission unreliable.
- [ ] **Fix Bug 2** (persist Tier-1 matches) — needed for Moodle UI to be useful.
- [ ] **Fix Bug 3** (drop `--reload` in prod compose).
- [ ] Pre-warm the embedding model in the worker image build (download `all-MiniLM-L6-v2` at build time, bake into image) — eliminates the 8-min first-run delay AND removes the stale-transaction window.
- [ ] Test Tier-2 escalation: craft a document that's semantically similar but not lexically (paraphrase) to confirm sentence-transformers + FAISS path actually runs.
- [ ] Hit Moodle UI at http://localhost:8080 (admin / Admin123!), install dualtier plugin, point it at `http://api:8000` with bearer `dev-secret-key-change-in-production`.
- [ ] End-to-end Moodle assignment test: create assignment, submit document via Moodle UI, verify detection result surfaces in assignment view.

## Key files referenced
- [docker-compose.yml](../../docker-compose.yml) — full stack including Moodle
- [docker-compose.dev.yml](../../docker-compose.dev.yml) — backend-only (no Moodle); used by previous session
- [backend/Dockerfile](../../backend/Dockerfile) — 2-stage build, CPU-only PyTorch
- [backend/entrypoint.sh](../../backend/entrypoint.sh) — runs `alembic upgrade head` then `exec "$@"`
- [moodle-plugin/plagiarism/dualtier/](../../moodle-plugin/plagiarism/dualtier/) — the Moodle plugin

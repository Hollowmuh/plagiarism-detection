# Plagiarism Detection System — Full Implementation Plan

**Project:** Developing an Affordable Plagiarism Detection System for University LMS
**Author:** Olomu Mueez Tolulope (190407042)
**Date:** 2026-05-15
**Architecture Reference:** MIILE backend (FastAPI + Celery + LTI 1.3 + ChromaDB)

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Project Structure](#2-project-structure)
3. [Phase 1 — Foundation (Weeks 1-2)](#3-phase-1--foundation-weeks-1-2)
4. [Phase 2 — Tier 1 Detection Engine (Weeks 3-4)](#4-phase-2--tier-1-detection-engine-weeks-3-4)
5. [Phase 3 — Dataset + Tier 2 Semantic Engine (Weeks 5-6)](#5-phase-3--dataset--tier-2-semantic-engine-weeks-5-6)
6. [Phase 4 — Moodle Plugin (Weeks 7-9)](#6-phase-4--moodle-plugin-weeks-7-9)
7. [Phase 5 — Evaluation (Weeks 9-11)](#7-phase-5--evaluation-weeks-9-11)
8. [Phase 6 — Communication (Week 12)](#8-phase-6--communication-week-12)
9. [Database Schema](#9-database-schema)
10. [API Surface](#10-api-surface)
11. [Celery Task Architecture](#11-celery-task-architecture)
12. [Docker Compose Topology](#12-docker-compose-topology)
13. [Detection Pipeline — Detailed Algorithm Specs](#13-detection-pipeline--detailed-algorithm-specs)
14. [Moodle Plugin File Structure](#14-moodle-plugin-file-structure)
15. [Dataset Construction Pipeline](#15-dataset-construction-pipeline)
16. [Evaluation Framework](#16-evaluation-framework)
17. [Configuration & Environment](#17-configuration--environment)
18. [Risk Mitigation](#18-risk-mitigation)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    MOODLE 4.x LMS                               │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  plagiarism_dualtier Plugin (PHP 8.1+)                   │   │
│  │  - Event observers (file_uploaded, content_uploaded)      │   │
│  │  - Ad-hoc tasks (submit to backend)                      │   │
│  │  - Scheduled task (poll results every 5 min)             │   │
│  │  - get_links() → similarity badge in gradebook           │   │
│  │  - report.php → detailed comparison view                 │   │
│  │  - settings.php → admin config (API URL, key, thresholds)│   │
│  └────────────────────────┬─────────────────────────────────┘   │
└───────────────────────────┼─────────────────────────────────────┘
                            │ HTTPS REST (Bearer token)
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│              DETECTION BACKEND (FastAPI)                         │
│                                                                  │
│  ┌─── API Layer (/api/v1) ───────────────────────────────────┐  │
│  │  POST /submissions         → 202 Accepted + queue task    │  │
│  │  GET  /submissions/{id}/status  → lightweight poll        │  │
│  │  GET  /submissions/{id}/results → similarity report       │  │
│  │  GET  /health                   → DB + Redis + worker     │  │
│  └───────────────────────────┬───────────────────────────────┘  │
│                               │                                  │
│  ┌─── Detection Pipeline ────▼───────────────────────────────┐  │
│  │                                                            │  │
│  │  ┌──────────┐    ┌─────────────────────────────────────┐  │  │
│  │  │  Text    │    │  TIER 1: Local Lexical Detection    │  │  │
│  │  │ Extract  │───▶│  ┌────────────┐  ┌──────────────┐  │  │  │
│  │  │ (PyMuPDF │    │  │ Winnowing  │  │   BM25       │  │  │  │
│  │  │  python- │    │  │ k=5, w=4   │  │   k1=1.5     │  │  │  │
│  │  │  docx)   │    │  │ Jaccard    │  │   b=0.75     │  │  │  │
│  │  └──────────┘    │  └─────┬──────┘  └──────┬───────┘  │  │  │
│  │                  │        └────────┬────────┘          │  │  │
│  │                  │                 ▼                    │  │  │
│  │                  │    c1(D) = max(norm_winnow, norm_bm25)│ │  │
│  │                  └─────────────────┬───────────────────┘  │  │
│  │                                    │                      │  │
│  │                  ┌─────────────────▼───────────────────┐  │  │
│  │                  │  GATING FUNCTION                     │  │  │
│  │                  │  c1 < τ_low  → ORIGINAL (stop)      │  │  │
│  │                  │  c1 > τ_high → PLAGIARISED (stop)   │  │  │
│  │                  │  else        → ESCALATE to Tier 2   │  │  │
│  │                  └─────────────────┬───────────────────┘  │  │
│  │                                    │ (~18-20% of cases)   │  │
│  │                  ┌─────────────────▼───────────────────┐  │  │
│  │                  │  TIER 2: Hybrid Semantic Detection   │  │  │
│  │                  │  ┌───────────────┐ ┌─────────────┐  │  │  │
│  │                  │  │ all-MiniLM-   │ │ BM25 scores │  │  │  │
│  │                  │  │ L6-v2 (384d)  │ │ (from T1)   │  │  │  │
│  │                  │  │ + FAISS IVFPQ │ │             │  │  │  │
│  │                  │  └──────┬────────┘ └──────┬──────┘  │  │  │
│  │                  │         └────────┬─────────┘         │  │  │
│  │                  │                  ▼                    │  │  │
│  │                  │  c2 = α·dense + (1-α)·sparse        │  │  │
│  │                  │  (α tuned on validation split)       │  │  │
│  │                  └──────────────────────────────────────┘  │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌─── Storage Layer ─────────────────────────────────────────┐  │
│  │  PostgreSQL 16  — submissions, results, documents, config │  │
│  │  Redis 7        — Celery broker + result backend + cache  │  │
│  │  FAISS (disk)   — IVFPQ index for 384-dim embeddings     │  │
│  │  S3/MinIO       — raw file storage                       │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌─── Async Workers (Celery) ────────────────────────────────┐  │
│  │  Queue: extraction  → extract_text_task                   │  │
│  │  Queue: detection   → tier1_detect_task, tier2_detect_task│  │
│  │  Queue: embedding   → generate_embeddings_task            │  │
│  │  Queue: indexing    → index_submission_task                │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### Key Architectural Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Vector store | FAISS IVFPQ (not ChromaDB) | Lower overhead for 384-dim, CPU-only, sub-ms query latency |
| Embedding model | all-MiniLM-L6-v2 (384d) | 22MB, 2000 sent/sec on CPU, within 2-3% of larger models on STS benchmarks |
| Sparse retrieval | rank-bm25 with periodic rebuild | Simple, well-tested; bm25s as upgrade path if speed needed |
| Fingerprinting | Winnowing (k=5, w=4) | Detection guarantee for matches >= 8 tokens, positional evidence |
| Fusion | Linear interpolation (not RRF) | 1 hyperparameter, decomposable for explainability |
| LMS integration | Moodle plagiarism plugin subsystem | Native gradebook rendering, event observers, standard API |
| Moodle-Backend comms | REST API + Bearer token | Matches MIILE pattern exactly — proven in production |
| Async processing | Celery + Redis | Matches MIILE pattern; ad-hoc tasks for submissions, scheduled task for polling |

### Reusable Patterns from MIILE

The following MIILE patterns transfer directly to this system:

1. **LTI 1.3 auth flow** — If LTI is needed (optional; plagiarism plugins use internal Moodle API, not LTI)
2. **Celery task routing** — Queue-per-task-type pattern with `task_routes` config
3. **Bearer + Session auth** — `core/auth.py` pattern for API protection
4. **Health endpoint** — `/health` checking DB + Redis + Celery workers
5. **Ingestion pipeline** — `ingest.chunk_document → ingest.generate_embedding_batch → ingest.store_in_chromadb` maps to `extract_text → generate_embeddings → index_in_faiss`
6. **ChromaDB degraded mode** — Same pattern for FAISS: detection falls back to Tier 1 only if FAISS unavailable
7. **S3 document storage** — Same upload + hash dedup pattern
8. **Docker Compose** — Same service topology (api, worker, redis, postgres)

---

## 2. Project Structure

```
plagiarism-detection/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                    # FastAPI app, lifespan, middleware
│   │   ├── config.py                  # Pydantic Settings (env-based)
│   │   ├── api/
│   │   │   ├── v1/
│   │   │   │   ├── __init__.py        # Aggregated v1 router
│   │   │   │   ├── submissions.py     # POST/GET submissions
│   │   │   │   ├── results.py         # GET results
│   │   │   │   └── health.py          # Health checks
│   │   ├── models/
│   │   │   ├── submission.py          # SQLAlchemy: Submission
│   │   │   ├── document.py            # SQLAlchemy: Document, DocumentChunk
│   │   │   ├── result.py              # SQLAlchemy: DetectionResult, SimilarityPair
│   │   │   └── fingerprint.py         # SQLAlchemy: DocumentFingerprint
│   │   ├── schemas/
│   │   │   ├── submission.py          # Pydantic request/response
│   │   │   └── result.py              # Pydantic result models
│   │   ├── services/
│   │   │   ├── text_extraction.py     # PyMuPDF + python-docx
│   │   │   ├── winnowing.py           # Winnowing fingerprinting engine
│   │   │   ├── bm25_service.py        # BM25 index + incremental updates
│   │   │   ├── embedding_service.py   # sentence-transformers encoding
│   │   │   ├── faiss_service.py       # FAISS IVFPQ index management
│   │   │   ├── tier1_detector.py      # Tier 1 pipeline orchestrator
│   │   │   ├── tier2_detector.py      # Tier 2 hybrid fusion
│   │   │   ├── gating.py             # Confidence gating function
│   │   │   └── detection_pipeline.py  # Full pipeline orchestrator
│   │   ├── core/
│   │   │   ├── auth.py                # Bearer token validation
│   │   │   ├── logging.py            # structlog JSON setup
│   │   │   └── exceptions.py
│   │   ├── db/
│   │   │   ├── session.py             # async sessionmaker
│   │   │   └── base.py                # DeclarativeBase
│   │   └── tasks/
│   │       ├── celery_app.py          # Celery instance + config
│   │       ├── extraction_tasks.py    # Text extraction tasks
│   │       ├── detection_tasks.py     # Tier 1 + Tier 2 tasks
│   │       ├── embedding_tasks.py     # Embedding generation tasks
│   │       └── indexing_tasks.py      # FAISS/BM25 index update tasks
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   ├── tests/
│   │   ├── test_winnowing.py
│   │   ├── test_bm25.py
│   │   ├── test_tier1.py
│   │   ├── test_tier2.py
│   │   ├── test_gating.py
│   │   ├── test_pipeline.py
│   │   └── test_api.py
│   ├── Dockerfile
│   ├── requirements.txt
│   └── .env.example
├── moodle-plugin/
│   └── plagiarism/
│       └── dualtier/
│           ├── version.php
│           ├── lib.php                # plagiarism_plugin_dualtier class
│           ├── settings.php           # Admin config
│           ├── report.php             # Full similarity report page
│           ├── db/
│           │   ├── install.xml        # XMLDB table definitions
│           │   ├── upgrade.php
│           │   ├── events.php         # Event observers
│           │   ├── tasks.php          # Scheduled task definitions
│           │   └── access.php         # Capabilities
│           ├── classes/
│           │   ├── observer.php       # Event handler
│           │   ├── api_client.php     # HTTP client for FastAPI
│           │   ├── task/
│           │   │   ├── submit_file.php      # Ad-hoc: send to backend
│           │   │   └── check_results.php    # Scheduled: poll results
│           │   └── privacy/
│           │       └── provider.php   # GDPR compliance
│           ├── lang/en/
│           │   └── plagiarism_dualtier.php
│           ├── pix/icon.svg
│           └── styles.css
├── evaluation/
│   ├── dataset/
│   │   ├── generate_dataset.py        # Dataset construction script
│   │   ├── perturbation.py           # Rule-based text perturbation
│   │   ├── paraphrase_generator.py   # GPT-4 paraphrase generation
│   │   ├── quality_control.py        # Length/language/dedup filters
│   │   └── data/
│   │       ├── sources/               # Original source documents
│   │       ├── submissions/           # Generated test submissions
│   │       ├── labels.csv             # Ground truth labels
│   │       └── splits/               # train/val/test splits
│   ├── baselines/
│   │   ├── local_only.py             # Baseline: Tier 1 only
│   │   ├── cloud_only.py             # Baseline: Tier 2 only
│   │   └── hybrid_static.py          # Baseline: always both tiers
│   ├── experiments/
│   │   ├── exp1_tier_resolution.py
│   │   ├── exp2_cost_accuracy.py
│   │   └── exp3_threshold_sensitivity.py
│   ├── metrics.py                    # Precision, recall, F1, bootstrap CI
│   └── plots.py                      # Visualization scripts
├── docker-compose.yml
├── docker-compose.dev.yml
└── docs/
    └── 2026-05-15/
        └── system_implementation_plan_1500.md   # This file
```

---

## 3. Phase 1 — Foundation (Weeks 1-2)

### Week 1: Project Scaffold + Infrastructure

**Deliverables:**
- [ ] Initialize Git repo with `.gitignore`, `README.md`
- [ ] Create FastAPI project structure (all directories, `__init__.py` files)
- [ ] Write `config.py` with Pydantic Settings for all environment variables
- [ ] Write `docker-compose.yml` with all 7 services (api, worker, redis, postgres, moodle, moodle-db, flower)
- [ ] Write multi-stage `Dockerfile` (Python 3.12-slim)
- [ ] Set up PostgreSQL with initial Alembic migration
- [ ] Implement `/health` endpoint (checks DB + Redis)
- [ ] Verify `docker compose up` brings up full stack

**config.py settings (minimum):**
```python
# Database
DATABASE_URL: str           # postgresql+asyncpg://user:pass@postgres:5432/plagiarism
DATABASE_URL_SYNC: str      # postgresql://user:pass@postgres:5432/plagiarism

# Redis / Celery
REDIS_URL: str              # redis://redis:6379/0
CELERY_BROKER_URL: str      # redis://redis:6379/0
CELERY_RESULT_BACKEND: str  # redis://redis:6379/1

# Auth
API_SECRET_KEY: str         # Shared secret for Moodle plugin auth

# Detection thresholds
TAU_LOW: float = 0.25       # Below = original
TAU_HIGH: float = 0.75      # Above = plagiarised
ALPHA: float = 0.6          # Dense fusion weight

# FAISS
FAISS_INDEX_PATH: str = "/data/faiss/index.faiss"
FAISS_NLIST: int = 256
FAISS_M: int = 48
FAISS_NPROBE: int = 32

# Winnowing
WINNOW_K: int = 5
WINNOW_W: int = 4
```

### Week 2: File Upload + Text Extraction

**Deliverables:**
- [ ] Implement `POST /api/v1/submissions/` endpoint (multipart file upload)
- [ ] Implement `text_extraction.py` service:
  - PDF extraction via PyMuPDF (fitz)
  - DOCX extraction via python-docx
  - TXT via built-in `open()` with `errors="replace"`
  - SHA-256 hash computation during upload for dedup
- [ ] Implement Celery `extract_text_task` on the `extraction` queue
- [ ] Write database models: `Submission`, `Document`
- [ ] Run Alembic migration for new tables
- [ ] Write unit tests for text extraction (PDF, DOCX, TXT)
- [ ] Implement `GET /api/v1/submissions/{id}/status` (lightweight poll)

**Success criteria:**
- Upload a PDF/DOCX through the API → get back extracted text
- Status endpoint returns current processing state
- Celery worker processes extraction asynchronously

---

## 4. Phase 2 — Tier 1 Detection Engine (Weeks 3-4)

### Week 3: Winnowing + BM25

**Deliverables:**
- [ ] Implement `winnowing.py` service:

```python
# Core algorithm parameters
K = 5           # k-gram size (noise threshold)
W = 4           # window size
BASE = 256      # Karp-Rabin base
MOD = 10**9 + 7 # Karp-Rabin modulus

# Pipeline: preprocess → kgrams → rolling_hash → winnow → fingerprint set
# Guarantee: detects any shared substring >= K + W - 1 = 8 tokens

# Preprocessing for natural language:
# 1. Unicode NFKD normalization
# 2. Lowercase
# 3. Strip ALL whitespace and punctuation (contiguous stream)
# DO NOT stem/lemmatize (breaks k-gram alignment)
# DO NOT remove stopwords (breaks contiguous substrings)
```

- [ ] Implement `IncrementalFingerprintIndex`:
  - Inverted index: `hash_value → set(doc_ids)`
  - `submit(doc_id, text) → List[MatchResult]` (query then insert)
  - Thread-safe with `threading.RLock`
  - Jaccard + Containment similarity
- [ ] Implement `bm25_service.py`:
  - Use `rank_bm25.BM25Okapi` with `k1=1.5, b=0.75`
  - SpaCy tokenization + lemmatization + stopword removal
  - Incremental corpus management with periodic rebuild
  - Min-max normalization with 95th-percentile outlier clipping
- [ ] Write unit tests: Winnowing (known fingerprint outputs), BM25 (known rankings)

### Week 4: Tier 1 Pipeline + Gating

**Deliverables:**
- [ ] Implement `tier1_detector.py`:
  - Accepts extracted text + corpus reference
  - Runs Winnowing fingerprinting against inverted index
  - Runs BM25 against corpus index
  - Computes `c1(D) = max(norm(S_winnow), norm(max_bm25))`
  - Returns confidence score + evidence passages
- [ ] Implement `gating.py`:

```python
def route(c1: float, tau_low: float, tau_high: float) -> str:
    if c1 < tau_low:
        return "TIER1_ORIGINAL"
    elif c1 > tau_high:
        return "TIER1_PLAGIARISED"
    else:
        return "ESCALATE_TO_TIER2"
```

- [ ] Implement Celery `tier1_detect_task`:
  - Extracts text (if not already done)
  - Runs Tier 1 detection
  - Applies gating function
  - If ORIGINAL or PLAGIARISED → store result, mark complete
  - If ESCALATE → chain to `tier2_detect_task`
- [ ] Implement `indexing_tasks.py`:
  - `index_submission_task`: adds new submission to Winnowing inverted index + BM25 corpus
  - Runs AFTER detection (so cross-submission works: query first, then insert)
- [ ] Wire Tier 1 API endpoint through full pipeline
- [ ] Write integration test: submit known-plagiarism doc → get TIER1_PLAGIARISED
- [ ] Write integration test: submit original doc → get TIER1_ORIGINAL

**Success criteria:**
- Submit a verbatim copy → detected at Tier 1 with high confidence
- Submit an original doc → classified as original at Tier 1
- New submission is indexed for future cross-submission detection

---

## 5. Phase 3 — Dataset + Tier 2 Semantic Engine (Weeks 5-6)

### Week 5: Dataset Construction + Embedding Pipeline

**Dataset (200 submissions):**

| Category | Count | Method |
|----------|-------|--------|
| Verbatim | 40 | Copy-paste from Wikipedia + open-access papers |
| Near-verbatim | 40 | Rule-based perturbation of verbatim set (10-20% synonym swap via WordNet, active→passive via SpaCy, punctuation changes) |
| Paraphrased | 60 | GPT-4 with manual review (discard ~15% for semantic fidelity; verify P-SP > 0.76 via embedding cosine) |
| Original | 60 | Anonymized past course submissions (strip PII) |

**Quality control pipeline:**
1. Length filter: 500-5,000 words
2. Language filter: fastText `lid218e` confidence > 0.95 (English only)
3. Near-duplicate removal: SimHash with Hamming distance threshold ≤ 3
4. 60/20/20 train/validation/test split (stratified by category)
5. Second-pass label review with 2-week separation
6. Cohen's kappa on 20-submission audit sample (target κ ≥ 0.80)

**Deliverables:**
- [ ] Implement `generate_dataset.py` with all 4 category generators
- [ ] Implement `perturbation.py` (WordNet synonym replacement, voice conversion, punctuation)
- [ ] Implement `paraphrase_generator.py` (GPT-4 Batch API for 50% discount)
- [ ] Implement `quality_control.py` (fastText + SimHash + length filters)
- [ ] Generate and freeze the 200-submission dataset with labels
- [ ] Create 60/20/20 stratified splits
- [ ] Implement `embedding_service.py`:

```python
# Model: all-MiniLM-L6-v2 (22MB, 384 dimensions)
# Load ONCE at worker startup, not per task
# normalize_embeddings=True (critical: enables cosine sim via dot product)
# Chunking: 256 tokens, 50-token overlap, sentence-boundary-aware
# Batch size on CPU: 32-64
# Set OMP_NUM_THREADS=4, TOKENIZERS_PARALLELISM=false
```

- [ ] Implement text chunking with source position tracking: `(doc_id, chunk_index, char_start, char_end)`

### Week 6: FAISS Index + Hybrid Fusion

**Deliverables:**
- [ ] Implement `faiss_service.py`:

```python
# Configuration for 384-dim embeddings:
d = 384                    # all-MiniLM-L6-v2 dimensionality
nlist = 256                # Voronoi cells (tune: 4*sqrt(N))
m = 48                     # subquantizers: 384/48 = 8 floats per sub-vector
nbits = 8                  # 256 centroids per subquantizer
nprobe = 32                # clusters probed at search time

# Use IndexFlatIP as quantizer (not L2) — normalized vectors, IP = cosine
# Training: need >= nlist * 40 = 10,240 vectors minimum
# Persistence: faiss.write_index / faiss.read_index
# Incremental adds: index.add() after training (IVF centroids fixed)
# add_with_ids() for custom ID mapping
```

- [ ] Implement `tier2_detector.py`:

```python
# Hybrid fusion for escalated submissions:
# 1. BM25 top-100 candidates (already computed in Tier 1)
# 2. FAISS top-100 candidates (dense retrieval)
# 3. Union candidate sets
# 4. Normalize: min-max with 95th-percentile clipping for BM25
#    Cosine similarity already in [0, 1] for normalized embeddings
# 5. Fuse: c2 = α * dense_norm + (1 - α) * sparse_norm
# 6. Return top-K with evidence passages

# Alpha tuning: grid search α ∈ {0.1, 0.2, ..., 0.9} on validation split
# Maximize F1-score
# Expected optimal: α ≈ 0.6 (emphasize semantic for paraphrase detection)
```

- [ ] Implement Celery `tier2_detect_task` and `generate_embeddings_task`
- [ ] Tune α on validation split (grid search)
- [ ] Tune τ_low, τ_high on validation split under constraints:
  - Escalation rate ρ ≤ 0.25
  - Tier 1 plagiarism precision ≥ 0.95
- [ ] Train FAISS index on development corpus
- [ ] Write integration test: submit paraphrased doc → escalated to Tier 2 → detected
- [ ] End-to-end pipeline test: submission → extraction → Tier 1 → gating → Tier 2 → result

**Success criteria:**
- Full dual-tier pipeline operational
- Paraphrased plagiarism detected via Tier 2
- α and τ thresholds tuned on validation data

---

## 6. Phase 4 — Moodle Plugin (Weeks 7-9)

### Week 7: Plugin Skeleton + Event Handling

**Deliverables:**
- [ ] Create plugin file structure under `moodle-plugin/plagiarism/dualtier/`
- [ ] Write `version.php`:

```php
$plugin->version   = 2026051500;
$plugin->requires  = 2023100900;  // Moodle 4.3+
$plugin->component = 'plagiarism_dualtier';
$plugin->maturity  = MATURITY_ALPHA;
$plugin->release   = '1.0.0';
```

- [ ] Write `lib.php` with `plagiarism_plugin_dualtier` class:
  - `get_links($linkarray)` — return similarity badge HTML
  - `get_form_elements_module($mform, $context, $modulename)` — enable/disable per activity
  - `save_form_elements($data)` — persist per-module config
  - `print_disclosure($cmid)` — student disclosure notice
- [ ] Write `db/events.php` — observe `assessable_uploaded` events from:
  - `\assignsubmission_file\event\assessable_uploaded`
  - `\assignsubmission_onlinetext\event\assessable_uploaded`
- [ ] Write `classes/observer.php` — queue ad-hoc task on submission event
- [ ] Write `db/install.xml` — tables: `plagiarism_dualtier_files`, `plagiarism_dualtier_config`
- [ ] Write `settings.php` — admin settings (API URL, API key, thresholds, enable/disable)
- [ ] Write `db/access.php` — capabilities: `viewreport`, `enable`
- [ ] Write `lang/en/plagiarism_dualtier.php` — all language strings
- [ ] Install plugin in Dockerized Moodle and verify it appears in admin

### Week 8: Backend Communication + Result Display

**Deliverables:**
- [ ] Write `classes/api_client.php`:
  - `submit_file(filename, content, metadata)` → POST to FastAPI
  - `get_result(submission_id)` → GET from FastAPI
  - Uses Moodle's built-in `curl` class (not raw PHP curl)
  - Bearer token from plugin settings
  - Base64-encode file content for JSON transport
- [ ] Write `classes/task/submit_file.php` (ad-hoc task):
  - Retrieve file from Moodle file storage
  - Call `api_client->submit_file()`
  - Store `external_id` in `plagiarism_dualtier_files`
- [ ] Write `classes/task/check_results.php` (scheduled task, every 5 min):
  - Query all records with `status = 'submitted'`
  - Poll FastAPI for each
  - Update `similarityscore` and `status` on completion
- [ ] Write `db/tasks.php` — register scheduled task
- [ ] Implement `get_links()` rendering:
  - Pending → "Checking..." spinner
  - Complete → colored badge (green < 30%, orange 30-70%, red > 70%)
  - Badge links to `report.php`
- [ ] Write `report.php` — detailed similarity report page:
  - Validates grading capability
  - Fetches detailed report from FastAPI
  - Renders matched passages with side-by-side comparison
  - Shows Tier 1 vs Tier 2 breakdown

### Week 9: Integration Testing

**Deliverables:**
- [ ] End-to-end test: student submits assignment in Moodle → plugin fires event → ad-hoc task calls FastAPI → detection runs → scheduled task polls result → badge appears in gradebook
- [ ] Cross-submission test:
  1. Student A submits at time T
  2. Student B submits paraphrased copy at T + 15 min
  3. System flags similarity within 5 seconds of B's submission
  4. Instructor dashboard shows cross-reference
  5. Repeat 5 times with different submission pairs
- [ ] Test admin settings: change thresholds → verify detection behavior changes
- [ ] Test error handling: FastAPI down → graceful degradation in Moodle
- [ ] Write `classes/privacy/provider.php` for GDPR compliance
- [ ] Write GDPR-compliant data export and deletion handlers

**Success criteria:**
- Full round-trip: Moodle → FastAPI → detection → results → Moodle gradebook
- Cross-submission detection works in real-time
- Instructor can view detailed similarity reports

---

## 7. Phase 5 — Evaluation (Weeks 9-11)

### Experiment 1: Tier Resolution Analysis (Tests H1)

**Hypothesis:** Tier 1 resolution rate ≥ 80%

**Procedure:**
1. Run all 40 test submissions through Tier 1
2. Record c1 scores for each
3. Apply gating function with tuned τ_low, τ_high
4. Compute resolution rate = fraction classified as ORIGINAL or PLAGIARISED
5. Report per-category breakdown

**Expected:**
- Verbatim: ~100% resolved at Tier 1
- Original: ~95% resolved at Tier 1
- Near-verbatim: ~70% resolved at Tier 1
- Paraphrased: ~20% resolved at Tier 1 (most escalate)
- Aggregate: ≥ 80%

### Experiment 2: Cost-Accuracy Trade-offs (Tests H2, H3)

**Configurations:**
| Config | Description |
|--------|-------------|
| (a) Local-only | Tier 1 only, no escalation |
| (b) Cloud-only | Tier 2 on every submission |
| (c) Hybrid-static | Always run both tiers |
| (d) Dual-tier | Proposed gated pipeline |

**Metrics per configuration:**
- Precision, Recall, F1-score (binary: plagiarised/original)
- Per-category F1
- Total cost using `C_total = ρ × N × c_cloud` (c_cloud = $0.10/1000 embeddings)
- End-to-end latency (p50, p95, p99)

**Statistical test:** Paired t-test on per-submission F1 contributions, α = 0.05 with Bonferroni correction across 3 pairwise comparisons (adjusted α = 0.0167)

**Bootstrap CI:** 1,000 resamples, 95% percentile intervals

### Experiment 3: Threshold Sensitivity + Real-Time Demo (Tests H4, H5)

**Threshold sweep:**
- τ_low ∈ {0.20, 0.25, 0.30}
- τ_high ∈ {0.70, 0.75, 0.80}
- 9 configurations → heatmap of (escalation rate, F1)

**Real-time demonstration:**
- Submit → detect → return results within 5-second p95 latency budget
- Cross-submission scenario repeated 5 times
- Measure on target hardware (16GB RAM, Intel Core i5, 256GB SSD)

---

## 8. Phase 6 — Communication (Week 12)

- [ ] Finalize thesis document (Chapter 4: Results, Chapter 5: Discussion)
- [ ] Prepare defense presentation
- [ ] Publish dataset + source code on GitHub under Apache 2.0 + CC BY 4.0
- [ ] Write deployment documentation (Docker Compose quick-start)
- [ ] Archive evaluation data and scripts for reproducibility

---

## 9. Database Schema

### submissions

| Column | Type | Notes |
|--------|------|-------|
| id | UUID (PK) | |
| external_id | VARCHAR(255) | Moodle assignment reference |
| course_id | VARCHAR(100) | |
| assignment_id | VARCHAR(100) | |
| user_id | VARCHAR(100) | Moodle user ID |
| status | ENUM | pending, extracting, detecting, completed, failed |
| tier_resolved | ENUM | tier1, tier2, null |
| celery_task_id | VARCHAR(255) | |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |
| error_message | TEXT | null unless failed |

### documents

| Column | Type | Notes |
|--------|------|-------|
| id | UUID (PK) | |
| submission_id | UUID (FK → submissions) | |
| filename | VARCHAR(255) | |
| file_path | VARCHAR(500) | S3 path |
| file_hash | VARCHAR(64) | SHA-256 for dedup |
| mime_type | VARCHAR(100) | |
| file_size_bytes | INTEGER | |
| extracted_text | TEXT | |
| word_count | INTEGER | |
| created_at | TIMESTAMP | |

### document_fingerprints

| Column | Type | Notes |
|--------|------|-------|
| id | UUID (PK) | |
| document_id | UUID (FK → documents) | UNIQUE |
| fingerprint_hashes | JSONB | Array of winnowing hash values |
| fingerprint_count | INTEGER | |
| created_at | TIMESTAMP | |

### document_chunks

| Column | Type | Notes |
|--------|------|-------|
| id | UUID (PK) | |
| document_id | UUID (FK → documents) | |
| chunk_index | INTEGER | |
| chunk_text | TEXT | |
| char_start | INTEGER | Position in source document |
| char_end | INTEGER | |
| embedding_vector | FLOAT[] | 384-dim (or stored in FAISS only) |
| created_at | TIMESTAMP | |

### detection_results

| Column | Type | Notes |
|--------|------|-------|
| id | UUID (PK) | |
| submission_id | UUID (FK → submissions) | UNIQUE |
| tier1_score | FLOAT | c1(D) |
| tier2_score | FLOAT | c2(D), null if not escalated |
| final_score | FLOAT | The decisive score |
| is_plagiarised | BOOLEAN | |
| escalated | BOOLEAN | |
| escalation_reason | VARCHAR(50) | |
| processing_time_ms | INTEGER | |
| created_at | TIMESTAMP | |

### similarity_pairs

| Column | Type | Notes |
|--------|------|-------|
| id | UUID (PK) | |
| result_id | UUID (FK → detection_results) | |
| source_document_id | UUID (FK → documents) | The matching corpus doc |
| similarity_score | FLOAT | 0.0 - 1.0 |
| match_type | VARCHAR(20) | winnowing, bm25, dense, hybrid |
| matched_segments | JSONB | Array of {source_start, source_end, query_start, query_end, text} |

---

## 10. API Surface

| Method | Path | Request | Response | Status |
|--------|------|---------|----------|--------|
| POST | `/api/v1/submissions/` | Multipart: file + metadata JSON (course_id, assignment_id, user_id) | `{submission_id, status: "pending"}` | 202 |
| GET | `/api/v1/submissions/{id}/status` | — | `{status, tier_resolved, processing_time_ms}` | 200 |
| GET | `/api/v1/submissions/{id}/results` | — | `{final_score, is_plagiarised, tier1_score, tier2_score, matches: [...]}` | 200 / 404 |
| GET | `/api/v1/submissions/` | `?course_id=X&assignment_id=Y&page=1&per_page=20` | Paginated list | 200 |
| DELETE | `/api/v1/submissions/{id}` | — | — | 204 |
| GET | `/api/v1/health` | — | `{status, db, redis, workers}` | 200 / 503 |
| GET | `/api/v1/health/live` | — | `{status: "alive"}` | 200 |
| GET | `/api/v1/health/ready` | — | `{status: "ready"}` | 200 / 503 |

**Auth:** All endpoints except `/health/live` require `Authorization: Bearer <api_key>` header.

**Error format:** `{"detail": "message", "code": "ERROR_CODE"}`

---

## 11. Celery Task Architecture

### Queues

| Queue | Tasks | Concurrency | Notes |
|-------|-------|-------------|-------|
| `extraction` | `extract_text_task` | 4 | I/O bound (file reading) |
| `detection` | `tier1_detect_task`, `tier2_detect_task` | 2 | CPU bound (hashing, scoring) |
| `embedding` | `generate_embeddings_task` | 1 | CPU bound (model inference), high memory |
| `indexing` | `index_submission_task` | 2 | Updates Winnowing + BM25 + FAISS indexes |
| `default` | Misc | 4 | Cleanup, notifications |

### Task Chain (per submission)

```
submit_file (Moodle ad-hoc task)
  └→ POST /api/v1/submissions/
       └→ extract_text_task (queue: extraction)
            └→ tier1_detect_task (queue: detection)
                 ├→ [if ORIGINAL or PLAGIARISED] → store_result + index_submission_task
                 └→ [if ESCALATE] → generate_embeddings_task (queue: embedding)
                      └→ tier2_detect_task (queue: detection)
                           └→ store_result + index_submission_task
```

### Configuration

```python
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    result_expires=86400,
    task_soft_time_limit=600,
    task_time_limit=900,
    worker_max_tasks_per_child=50,   # Recycle for ML memory leaks
    task_routes={
        "tasks.extraction_tasks.*": {"queue": "extraction"},
        "tasks.detection_tasks.*": {"queue": "detection"},
        "tasks.embedding_tasks.*": {"queue": "embedding"},
        "tasks.indexing_tasks.*": {"queue": "indexing"},
    },
)
```

### Worker Startup

```python
# Load ML model ONCE at worker startup, not per task
from sentence_transformers import SentenceTransformer

_model = None

def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer(
            'all-MiniLM-L6-v2',
            device='cpu'
        )
    return _model
```

### Environment Variables for CPU Optimization

```bash
OMP_NUM_THREADS=4
MKL_NUM_THREADS=4
TOKENIZERS_PARALLELISM=false
```

---

## 12. Docker Compose Topology

```yaml
services:
  postgres:
    image: postgres:16-alpine
    volumes: [pgdata:/var/lib/postgresql/data]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U plagiarism"]
      interval: 5s

  redis:
    image: redis:7-alpine
    command: redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]

  api:
    build: ./backend
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
    ports: ["8000:8000"]
    depends_on:
      postgres: {condition: service_healthy}
      redis: {condition: service_healthy}
    volumes: [faiss_data:/data/faiss]

  celery-worker:
    build: ./backend
    command: celery -A app.tasks.celery_app worker
             --queues=extraction,detection,embedding,indexing,default
             --concurrency=4
    depends_on: [api]
    volumes: [faiss_data:/data/faiss]
    deploy:
      resources:
        limits: {memory: 4G}
    environment:
      OMP_NUM_THREADS: 4
      MKL_NUM_THREADS: 4
      TOKENIZERS_PARALLELISM: "false"

  celery-beat:
    build: ./backend
    command: celery -A app.tasks.celery_app beat --loglevel=info
    depends_on: [celery-worker]

  flower:
    build: ./backend
    command: celery -A app.tasks.celery_app flower --port=5555
    ports: ["5555:5555"]

  moodle:
    image: bitnami/moodle:4.4
    ports: ["8080:8080"]
    depends_on: [moodle-db]
    volumes:
      - ./moodle-plugin/plagiarism/dualtier:/bitnami/moodle/plagiarism/dualtier
      - moodle_data:/bitnami/moodle

  moodle-db:
    image: postgres:16-alpine
    volumes: [moodle_pgdata:/var/lib/postgresql/data]

volumes:
  pgdata:
  moodle_pgdata:
  moodle_data:
  faiss_data:
```

---

## 13. Detection Pipeline — Detailed Algorithm Specs

### 13.1 Winnowing Fingerprinting

```
Input:  raw text string
Output: Set[(hash_value, position)]

Step 1 — Preprocess:
  - Unicode NFKD normalize
  - Lowercase
  - Strip ALL whitespace and punctuation → contiguous alphanumeric stream

Step 2 — K-grams (k=5):
  - Generate all contiguous substrings of length 5
  - Document of length n produces (n - 5 + 1) k-grams

Step 3 — Karp-Rabin Rolling Hash:
  - BASE = 256, MOD = 10^9 + 7
  - First hash: O(k), each subsequent: O(1) via rolling
  - Total: O(n)

Step 4 — Winnowing (w=4):
  - Slide window of size 4 over hash array
  - Select minimum hash per window (rightmost on tie)
  - Record only if different from previous selection
  - Fingerprint density: within 33% of theoretical lower bound

Guarantee: Any shared substring ≥ k + w - 1 = 8 tokens is detected.

Similarity: Jaccard = |F(A) ∩ F(B)| / |F(A) ∪ F(B)|
Containment: C(A,B) = |F(A) ∩ F(B)| / |F(A)|
```

### 13.2 BM25 Ranking

```
Preprocessing: SpaCy tokenize → lemmatize → strip stopwords
Parameters: k1 = 1.5, b = 0.75

Score(D, Q) = Σ_t [ IDF(t) × f(t,D)×(k1+1) / (f(t,D) + k1×(1-b+b×|D|/avgdl)) ]
IDF(t) = log((N - n(t) + 0.5) / (n(t) + 0.5) + 1)

Index: Incremental corpus management
  - New documents append to corpus list
  - Rebuild BM25Okapi index periodically (or on each add for small corpus)
  - For production: consider bm25s with mmap for persistence

Normalization: Min-max with 95th-percentile outlier clipping
  scores_clipped = clip(scores, 0, percentile(scores, 95))
  normalized = (scores_clipped - min) / (max - min)
```

### 13.3 Tier 1 Confidence Score

```
c1(D) = max(
  norm(S_winnow(D, C)),     # Winnowing Jaccard against best match
  norm(max_{di ∈ C} BM25(D, di))  # Best BM25 score, normalized
)

Both components: min-max normalized to [0, 1] using percentile bounds
from calibration split (prevents outlier compression).
```

### 13.4 Gating Function

```
route(D) =
  TIER1_ORIGINAL     if c1(D) < τ_low     (default 0.25)
  ESCALATE_TO_TIER2  if τ_low ≤ c1(D) ≤ τ_high
  TIER1_PLAGIARISED  if c1(D) > τ_high    (default 0.75)

Tuning constraints:
  - Escalation rate ρ ≤ 0.25
  - TIER1_PLAGIARISED precision ≥ 0.95
```

### 13.5 Dense Embedding Generation

```
Model: all-MiniLM-L6-v2 (384 dimensions, 22MB)
Chunking: 256 tokens, 50-token overlap, sentence-boundary-aware
  - Preserve chunk-to-source mapping: (doc_id, chunk_index, char_start, char_end)

Encoding:
  model.encode(passages, batch_size=32, normalize_embeddings=True, convert_to_numpy=True)
  # normalize_embeddings=True → inner product = cosine similarity

CPU optimization:
  - Load model once at worker startup
  - OMP_NUM_THREADS=4
  - Pre-sort passages by length to minimize padding waste
  - ONNX Runtime backend for 20-50% speedup (optional)
```

### 13.6 FAISS Index

```
Type: IndexIVFPQ
  d = 384, nlist = 256, m = 48, nbits = 8, nprobe = 32

Quantizer: IndexFlatIP (inner product = cosine for normalized vectors)

Training: Need ≥ 10,240 vectors (nlist × 40)
  - If corpus smaller: use IndexFlatIP (exact search) instead

Search: query → top-50 nearest passages → downstream re-ranking
  Achieves >95% recall@50 vs exact search at sub-ms query latency

Persistence: faiss.write_index / faiss.read_index to shared volume
Incremental: index.add_with_ids() after training (centroids fixed)
```

### 13.7 Tier 2 Hybrid Fusion

```
For each escalated submission D:
  1. BM25 top-100 candidates (reuse from Tier 1)
  2. FAISS top-100 candidates
  3. Union candidate sets, discard -1 (FAISS no-match marker)
  4. For each candidate di:
     - sparse_score = BM25(D, di), normalized with robust min-max
     - dense_score = cosine(embed(D), embed(di)), already in [0,1]
  5. fused_score = α × dense_score + (1 - α) × sparse_score
  6. c2(D) = max(fused_score over all candidates)

α tuning: grid search {0.1, 0.2, ..., 0.9} on validation split
  Maximize F1. Expected optimal: α ≈ 0.6
```

### 13.8 Cost Model

```
C_total(N) = ρ × N × c_cloud

Where:
  N = total submissions in billing period
  ρ = escalation rate (target ≤ 0.20)
  c_cloud = $0.10 / 1000 submissions (embedding API cost)

Projected: 82% resolved locally → ρ = 0.18
  c_cloud = $0.10/1000
  Cost per 100 submissions = 0.18 × 100 × $0.0001 = $0.0018 ≈ $0.002

Cloud-only baseline: $0.10/1000 × 100 = $0.01
Saving: (1 - 0.18) = 82% cost reduction
```

---

## 14. Moodle Plugin File Structure

### Event Flow

```
Student submits assignment
  → Moodle fires \assignsubmission_file\event\assessable_uploaded
  → plagiarism_dualtier_observer::file_uploaded()
  → Queues ad-hoc task: submit_file
  → submit_file::execute():
      - Retrieves file from Moodle File API
      - Calls api_client->submit_file() → POST to FastAPI
      - Stores external_id in plagiarism_dualtier_files table
  → check_results scheduled task (every 5 min):
      - Polls all pending submissions
      - Updates similarity_score and status on completion
  → Instructor opens grading page
  → Moodle calls plagiarism_get_links()
  → get_links() returns colored badge + link to report.php
  → report.php shows detailed similarity comparison
```

### Key Tables (install.xml)

**plagiarism_dualtier_files:**
- id, cmid, userid, identifier (content hash), externalid (FastAPI submission_id)
- status (pending/submitted/complete/error)
- similarityscore (float), tier_resolved (tier1/tier2)
- reportdata (JSON — cached matches for report.php)
- timecreated, timemodified

**plagiarism_dualtier_config:**
- id, cmid, enabled (bool)

### Settings (settings.php)

| Setting | Type | Default |
|---------|------|---------|
| enabled | checkbox | 0 |
| apiurl | text (URL) | http://localhost:8000/api/v1 |
| apikey | password | (empty) |
| threshold | int | 25 (percentage to flag) |
| crosscheck | checkbox | 1 |
| tau_low | text | 0.25 |
| tau_high | text | 0.75 |

---

## 15. Dataset Construction Pipeline

```
Step 1: Collect Sources
  ├── Wikipedia articles (10 topics × 2 articles)  → 20 sources
  ├── Open-access papers (ArXiv, DOAJ)              → 20 sources
  └── Anonymized past submissions (departmental OK) → 60 originals

Step 2: Generate Verbatim (40)
  - Insert 1-3 unaltered paragraphs from sources into otherwise original text
  - Label: category=verbatim, plagiarism=1, source_ref=X

Step 3: Generate Near-Verbatim (40)
  - Start from verbatim set
  - Apply perturbation.py:
    a. WordNet synonym replacement at 10-20% of content words
    b. Active→passive voice conversion via SpaCy dependency parsing
    c. Random punctuation changes (semicolons→periods, quote style)
  - Label: category=near_verbatim, plagiarism=1

Step 4: Generate Paraphrased (60)
  - Send source paragraphs to GPT-4 Batch API
  - Prompt: "Paraphrase preserving meaning. Use different vocabulary and structure."
  - Verify: cosine similarity via all-MiniLM-L6-v2 > 0.76 (P-SP threshold)
  - Manual review: discard ~15% that drift semantically
  - Label: category=paraphrased, plagiarism=1

Step 5: Quality Control
  - Length filter: 500-5,000 words only
  - Language: fastText lid218e confidence > 0.95
  - Dedup: SimHash Hamming distance > 3 between all pairs in original set
  - Encoding: UTF-8 validated

Step 6: Split
  - Stratified 60/20/20 by category
  - Train: 120, Validation: 40, Test: 40
  - Fixed random seed for reproducibility

Step 7: Label Verification
  - Second-pass review after 2-week separation
  - Cohen's kappa on 20-submission audit (target κ ≥ 0.80)
```

---

## 16. Evaluation Framework

### Metrics

| Metric | Formula | Purpose |
|--------|---------|---------|
| Precision | TP / (TP + FP) | False positive control (critical for academic use) |
| Recall | TP / (TP + FN) | Detection coverage |
| F1-score | 2 × P × R / (P + R) | Headline metric |
| Per-category F1 | F1 for each of 4 categories | Diagnose failure modes |
| Escalation rate (ρ) | N_esc / N | Cost driver |
| Latency | p50, p95, p99 over 200 measurements | Real-time feasibility |
| Cost | ρ × N × c_cloud | Per-1000-submission cost |

### Bootstrap Confidence Intervals

```python
from scipy.stats import bootstrap
import numpy as np

def compute_f1_with_ci(y_true, y_pred, n_bootstrap=1000, ci=0.95):
    # Compute point estimate
    f1 = f1_score(y_true, y_pred)

    # Bootstrap
    rng = np.random.default_rng(42)
    f1_samples = []
    for _ in range(n_bootstrap):
        indices = rng.choice(len(y_true), size=len(y_true), replace=True)
        f1_boot = f1_score(y_true[indices], y_pred[indices])
        f1_samples.append(f1_boot)

    lower = np.percentile(f1_samples, (1-ci)/2 * 100)
    upper = np.percentile(f1_samples, (1+ci)/2 * 100)
    return f1, lower, upper
```

### Statistical Testing

```python
from scipy.stats import ttest_rel
from statsmodels.stats.multitest import multipletests

# Paired t-test for each baseline comparison
# 3 comparisons: dual-tier vs {local-only, cloud-only, hybrid-static}
# Bonferroni-corrected α = 0.05 / 3 = 0.0167

p_values = [
    ttest_rel(dualtier_scores, baseline_scores).pvalue
    for baseline_scores in [local_scores, cloud_scores, hybrid_scores]
]
reject, corrected_p, _, _ = multipletests(p_values, method='bonferroni')
```

### Reporting Format

```
System achieved F1 = 0.84 (95% CI: [0.81, 0.87]),
with 82% resolved at Tier 1 (ρ = 0.18).
Cloud cost: $0.02/100 submissions vs $0.10 baseline (80% reduction).
Paired bootstrap (B=1000): difference = 0.03 (95% CI: [0.01, 0.05]), p < 0.01.
```

---

## 17. Configuration & Environment

### .env.example

```bash
# Database
POSTGRES_USER=plagiarism
POSTGRES_PASSWORD=changeme
POSTGRES_DB=plagiarism
DATABASE_URL=postgresql+asyncpg://plagiarism:changeme@postgres:5432/plagiarism
DATABASE_URL_SYNC=postgresql://plagiarism:changeme@postgres:5432/plagiarism

# Redis
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/1

# Auth
API_SECRET_KEY=your-secret-key-here

# Detection
TAU_LOW=0.25
TAU_HIGH=0.75
ALPHA=0.6
WINNOW_K=5
WINNOW_W=4

# FAISS
FAISS_INDEX_PATH=/data/faiss/index.faiss
FAISS_NLIST=256
FAISS_M=48
FAISS_NPROBE=32

# Embedding model
EMBEDDING_MODEL=all-MiniLM-L6-v2
EMBEDDING_DEVICE=cpu
CHUNK_SIZE=256
CHUNK_OVERLAP=50

# CPU optimization
OMP_NUM_THREADS=4
MKL_NUM_THREADS=4
TOKENIZERS_PARALLELISM=false

# Moodle
MOODLE_URL=http://moodle:8080
```

### requirements.txt (key dependencies)

```
# Web framework
fastapi>=0.110
uvicorn[standard]>=0.29
python-multipart

# Database
sqlalchemy[asyncio]>=2.0
asyncpg>=0.29
alembic>=1.13
psycopg2-binary>=2.9

# Background work
celery[redis]>=5.3
redis>=5.0
flower>=2.0

# NLP & Detection
rank-bm25>=0.2.2
spacy>=3.7
sentence-transformers>=2.3
faiss-cpu>=1.7.4
numpy<2.0

# Document processing
pymupdf>=1.23
python-docx>=1.1

# Evaluation
scikit-learn>=1.4
scipy>=1.12
matplotlib>=3.8
pandas>=2.2

# Monitoring
structlog>=24.1
prometheus-fastapi-instrumentator>=7.0

# Testing
pytest>=8.0
pytest-asyncio>=0.23
httpx>=0.27
coverage>=7.4
```

---

## 18. Risk Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| FAISS training data insufficient (<10K vectors) | HIGH for small corpus | Medium | Fall back to IndexFlatIP (exact search) for corpus <10K. IVFPQ only for production-scale. |
| Moodle plugin fails to install | Medium | HIGH | Test installation in Week 7 before building features. Have standalone web UI as fallback. |
| Embedding model too slow on CPU | Low | Medium | all-MiniLM-L6-v2 is 2000 sent/sec on CPU. If still slow: enable ONNX backend (20-50% speedup). |
| BM25 rebuild latency spikes | Low | Low | Rebuild in background task. Serve stale index during rebuild. Consider bm25s with mmap. |
| False positives on legitimate similar work | Medium | HIGH | Tier 1 precision constraint ≥ 0.95. Manual review step in instructor dashboard. |
| Dataset too small for threshold tuning | Medium | Medium | Use leave-one-out cross-validation on validation split. Report sensitivity analysis. |
| Scope creep | HIGH | HIGH | Follow phased approach strictly. MVP (Tier 1 + API) by Week 4 is non-negotiable. |
| Docker memory limits hit by ML model | Medium | Medium | `worker_max_tasks_per_child=50` for Celery recycling. 4GB memory limit per worker. |

---

## Summary: Critical Path

```
Week 1-2: FastAPI + Docker + Text Extraction          → CAN DEMO file upload
Week 3-4: Winnowing + BM25 + Gating                   → CAN DEMO Tier 1 detection
Week 5-6: Dataset + Embeddings + FAISS + Fusion        → CAN DEMO full dual-tier pipeline
Week 7-9: Moodle plugin + Integration testing          → CAN DEMO end-to-end in Moodle
Week 9-11: Experiments + Statistical analysis          → CAN PRESENT evaluation results
Week 12:  Thesis + Defense + Open-source release       → DONE
```

**The #1 rule: Working software at every phase boundary. Never go more than 2 weeks without a demonstrable milestone.**

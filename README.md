# Dual-Tier Plagiarism and AI-Generated Content Detection System

An enterprise-grade, cost-optimized plagiarism and AI text detection platform integrated natively with the Moodle Learning Management System (LMS).

Designed as an academic project, this system implements a hierarchical, dual-tier detection pipeline combined with an AI-generated content classifier to achieve high detection accuracy while minimizing computational latency and vector search overhead.

---

## Architecture Overview

The system uses a tiered escalation pipeline:

```
                  Incoming Submission
                          │
                          ▼
               ┌─────────────────────┐
               │  Text Extraction    │
               └──────────┬──────────┘
                          │
                          ▼
         ┌─────────────────────────────────┐
         │ Tier 1: Lexical Screening       │
         │ (Winnowing Fingerprints + BM25) │
         └────────────────┬────────────────┘
                          │
             ┌────────────┴────────────┐
             │                         │
     Similarity < τ_low        Similarity > τ_high
             │                         │
             ▼                         ▼
      [Mark Clean]              [Mark Plagiarized]
             │
      τ_low ≤ Similarity ≤ τ_high (Escalation)
             │
             ▼
         ┌─────────────────────────────────┐
         │ Tier 2: Deep Semantic Analysis  │
         │ (SBERT Embeddings + FAISS +     │
         │  BM25 Hybrid Fusion Scoring)    │
         └────────────────┬────────────────┘
                          │
                          ▼
         ┌─────────────────────────────────┐
         │ Stored Result + Moodle Report   │
         └─────────────────────────────────┘

   In parallel, on a separate worker (advisory only):
   AI-authorship classifier ──► ai_detection_results
```

### 1. Tier 1: Fast Lexical Screening
- **Algorithm**: Rabin-Karp hashing with Winnowing windowed fingerprinting.
- **Purpose**: Rapidly detects exact and near-verbatim copies with low latency. Submissions clearly below the lower threshold ($\tau_{low}$) are marked original without incurring heavy model computation.

### 2. Tier 2: Deep Semantic Retrieval & Hybrid Fusion
- **Algorithm**: Dense sentence embeddings (Sentence-Transformers / SBERT) indexed via FAISS (Facebook AI Similarity Search) combined with BM25 sparse lexical ranking.
- **Fusion**: Score fusion ($\alpha \cdot \text{Dense} + (1 - \alpha) \cdot \text{BM25}$) to capture heavy paraphrasing, synonym replacement, and concept borrowing.

### 3. AI Detection Tier
- **Algorithm**: Sequence classification with a fine-tuned RoBERTa model (`Hello-SimpleAI/chatgpt-detector-roberta`) to estimate whether text was machine generated.
- **Output**: One document-level probability and a verdict (likely human, uncertain, likely AI), computed on the first 512 tokens.
- **Advisory only**: It runs in parallel with plagiarism detection on its own worker, is stored separately, and never changes the plagiarism score. AI detectors have known false positives, so the report shows it with a disclaimer.

### 4. Moodle LMS Integration (`moodle-plugin/`)
- Native Moodle plagiarism plugin (`plagiarism_dualtier`) using the standard Moodle plagiarism API and the `assessable_uploaded` events of file and online-text submissions.
- Asynchronous processing: the plugin uploads through Moodle ad-hoc tasks, then polls for the result (`poll_result` every 15 seconds, with `check_results` as a 5-minute fallback).
- Instructor report view with a gauge score, tier breakdown, matched passages side by side, and the separate advisory AI-authorship score.

---

## Repository Structure

```
├── backend/                  # FastAPI & Celery detection backend
│   ├── alembic/              # Database schema migrations
│   ├── app/
│   │   ├── api/v1/           # REST endpoints (submissions, health, results)
│   │   ├── core/             # Auth, logging, exceptions
│   │   ├── db/               # PostgreSQL async/sync sessions & models
│   │   ├── schemas/          # Pydantic request/response schemas
│   │   ├── services/         # Winnowing, SBERT/FAISS, BM25, AI detector
│   │   └── tasks/            # Celery worker async detection pipelines
│   ├── tests/                # Comprehensive unit and integration test suite
│   ├── Dockerfile            # Backend container definition
│   └── requirements.txt      # Python dependencies
├── moodle-plugin/            # Moodle LMS Plagiarism Plugin (plagiarism_dualtier)
│   └── plagiarism/dualtier/  # PHP plugin source (classes, db, lang, UI reports)
├── evaluation/               # Benchmark experiments, datasets, and baselines
│   ├── baselines/            # Cloud-only, local-only, and hybrid baselines
│   ├── dataset/              # Dataset generator, paraphraser, splits
│   ├── experiments/          # Empirical threshold sweeps and accuracy tests
│   └── reports/              # Benchmark analysis reports
├── docker-compose.yml        # Multi-service production deployment
├── docker-compose.dev.yml    # Development deployment configuration
├── moodle-nginx.conf         # Reverse proxy configuration
└── .env.example              # Environment variables template
```

---

## Quick Start

### Prerequisites
- [Docker](https://docs.docker.com/get-docker/) (Engine 20.10+)
- [Docker Compose](https://docs.docker.com/compose/) (v2.0+)

### 1. Environment Setup
Copy the example environment configuration:
```bash
cp .env.example .env
```
Update any secrets in `.env` as required (database credentials, Celery broker URLs, API secret keys).

### 2. Start Services
Launch the entire stack using Docker Compose:
```bash
docker compose up -d
```

The stack launches:
- **API Backend**: `http://localhost:8000` (Swagger docs at `/docs`)
- **Celery Worker**: Distributed task processing for heavy neural embeddings & FAISS lookups
- **PostgreSQL**: Submissions metadata, document chunks, and similarity results
- **Redis**: Task queue message broker and caching layer
- **Moodle LMS**: `http://localhost:8080`, started by the same compose file

The first start downloads two machine-learning models (about 1 to 2 GB in total), so the workers take a few minutes to become ready.

### 3. Verify System Health
```bash
curl http://localhost:8000/api/v1/health
```

---

## Moodle Plugin Installation

1. Copy or symlink `moodle-plugin/plagiarism/dualtier` into your Moodle installation's `plagiarism/` directory:
   ```bash
   cp -r moodle-plugin/plagiarism/dualtier /path/to/moodle/plagiarism/dualtier
   ```
2. Navigate to your Moodle administrator dashboard: **Site Administration → Notifications** to complete the database upgrade.
3. Enable the plugin under **Site Administration → Plugins → Plagiarism Prevention → Dual-Tier Plagiarism Settings**.
4. Set the API URL to `http://api:8000/api/v1` and the API key to the same value as `API_SECRET_KEY`.
5. Turn on Moodle's core switch under **Site administration → Advanced features → Enable plagiarism plugins**, enable the plugin on each assignment, and make sure Moodle cron runs frequently, because uploads and result polling run as Moodle background tasks.

---

## Running Backend Tests

Run the test suite inside the backend directory or container:
```bash
# Inside local Python virtual environment
cd backend
pytest -v

# Or via Docker
docker compose exec api pytest -v
```

---

## Academic Citation & License

This project was developed as a final year B.Sc. project in Systems Engineering at the University of Lagos.
Released under the MIT License.

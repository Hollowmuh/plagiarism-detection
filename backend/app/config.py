from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Database ──────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://plagiarism:changeme@localhost:5432/plagiarism"
    DATABASE_URL_SYNC: str = "postgresql://plagiarism:changeme@localhost:5432/plagiarism"

    # ── Redis / Celery ────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    # ── Auth ──────────────────────────────────────────────────
    API_SECRET_KEY: str = "change-this-to-a-random-secret-key"

    # ── Detection thresholds ──────────────────────────────────
    # 0.30, not 0.25: re-tuned 2026-07-04 after fixing a dataset-leakage bug
    # in the evaluation corpus (evaluation/reports/00_dataset_reconciliation.md's
    # addendum). A threshold re-sweep against the corrected corpus
    # (evaluation/experiments/exp1b_threshold_resweep.py) found submissions
    # scoring in [0.25, 0.30) are never genuine plagiarism cases in this
    # corpus, so resolving them directly as TIER1_ORIGINAL instead of
    # escalating loses zero accuracy while reducing escalation rate (cost).
    TAU_LOW: float = 0.30
    # 0.68, not the textbook-round 0.75: tuned empirically against the
    # evaluation/ corpus (val split, F1 optimum plateau 0.67-0.72) after
    # fixing a tier2 doc/chunk-id mismatch bug that previously pinned scores
    # near alpha regardless of true similarity. Re-tune if the embedding
    # model, corpus, or tier2 fusion logic changes.
    TAU_HIGH: float = 0.68
    ALPHA: float = 0.6

    # ── Structural verification (stopword-skeleton n-grams) ────
    # Confirmation-only signal, see backend/app/services/structural_detector.py
    # and evaluation/reports/04_exp3_threshold_sensitivity.md Addendum 6.
    # Runs ONLY when a Tier 2 score falls in [STRUCTURAL_TAU_VERIFY, TAU_HIGH]
    # (i.e. suspicious but not yet confident enough to auto-confirm) --
    # never on its own, never widening what counts as "escalated".
    #
    # DEFAULT IS FALSE. Dual-corpus validation (Addendum 6) found this
    # recovers real recall on the peer-matching corpus (0.417->0.542,
    # precision held at 1.000) but introduces false positives on the
    # larger, richer source-matching corpus (precision 1.000->0.885) at
    # every threshold tested, including a "require 2 corroborating
    # sentence pairs" refinement -- the false/true positive skeleton-score
    # distributions genuinely overlap on this dataset, so no single
    # threshold or aggregation cleanly separates both corpora. Root cause:
    # richer source documents have far more candidate sentence pairs,
    # so a "max over all pairs" comparison is more likely to hit a
    # coincidental match by chance alone (a multiple-comparisons problem).
    #
    # Addendum 7 (2026-07-11): the named future-work fix (anchoring the
    # comparison to the specific chunk Tier 2 matched, instead of the
    # whole document) was built -- see Tier2Detector's best_submission_
    # chunk/best_source_chunk_index and this call site's chunk-scoped
    # match_text in detection_pipeline.py. It measurably helps (source-
    # matching precision 0.885->0.920) but doesn't fully close the gap
    # (still short of the ~1.000 this system holds everywhere else) --
    # a 256-word chunk can still contain several qualifying sentences,
    # so the multiple-comparisons problem shrinks, not disappears.
    # STILL FALSE. Sentence-pair anchoring (not just chunk anchoring)
    # is the next candidate fix, not yet attempted -- would need FAISS
    # indexed at sentence, not chunk, granularity.
    STRUCTURAL_ENABLED: bool = False
    STRUCTURAL_TAU_VERIFY: float = 0.60
    STRUCTURAL_SKELETON_THRESHOLD: float = 0.30
    STRUCTURAL_NGRAM_N: int = 4

    # ── Winnowing ─────────────────────────────────────────────
    WINNOW_K: int = 5
    WINNOW_W: int = 4

    # ── FAISS ─────────────────────────────────────────────────
    FAISS_INDEX_PATH: str = "/data/faiss/index.faiss"
    FAISS_NLIST: int = 256
    FAISS_M: int = 48
    FAISS_NPROBE: int = 32

    # ── Embedding ─────────────────────────────────────────────
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    EMBEDDING_DEVICE: str = "cpu"
    CHUNK_SIZE: int = 256
    CHUNK_OVERLAP: int = 50

    # ── AI-generated-text detection ──────────────────────────────
    # Independent, advisory-only signal -- NOT part of the tier1/tier2
    # source-matching pipeline. See docs/2026-07-01/ai_detection_tier_1426.md
    # for why this is a separate axis and the false-positive/ESL-bias
    # caveats that make this advisory rather than a pass/fail verdict.
    AI_DETECTOR_ENABLED: bool = True
    AI_DETECTOR_MODEL: str = "Hello-SimpleAI/chatgpt-detector-roberta"
    AI_DETECTOR_DEVICE: str = "cpu"
    AI_DETECTOR_MAX_LENGTH: int = 512
    AI_DETECTOR_TAU_LOW: float = 0.25
    AI_DETECTOR_TAU_HIGH: float = 0.75

    # ── CORS ──────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = ["http://localhost:8080", "http://localhost:3000"]

    # ── File upload ───────────────────────────────────────────
    MAX_UPLOAD_SIZE_MB: int = 50
    UPLOAD_DIR: str = "/data/uploads"


settings = Settings()

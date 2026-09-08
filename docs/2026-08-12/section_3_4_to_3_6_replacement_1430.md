# §3.4–§3.6 replacement/patch prose, ready to paste

Each subsection below is either a full replacement or a marked patch to the existing text. Formulas verified directly against the deployed code (`backend/app/services/tier1_detector.py`, `tier2_detector.py`, `bm25_service.py`, `winnowing.py`, `embedding_service.py`, `faiss_service.py`).

---

## 3.4 System Architecture

Keep the existing opening paragraph unchanged (2-tier pipeline behind a thin Moodle plugin layer; gating decides escalation; most submissions stop at Tier 1).

### 3.4.1 Tier 1: Local Lexical Detection — patch

Keep the first two sentences. Replace the third:

> ~~The Tier 1 confidence score is the maximum normalised similarity returned by either component.~~
>
> The Tier 1 confidence score combines both components asymmetrically: `c1(D) = max(containment(D), min(BM25_norm(D), 0.6))`. BM25's contribution is deliberately capped at 0.6, below the plagiarism threshold defined in §3.4.2, so that lexical or topical overlap alone can never trigger a direct plagiarism verdict — a BM25-dominated match can only route to Tier 2 for semantic verification, never resolve as plagiarised on its own. Only the Winnowing containment signal, which measures direct textual reuse rather than general topical relevance, can resolve a submission as plagiarised at Tier 1 without escalation.

### 3.4.2 Gating Function — patch

Keep the first sentence (3-region partition). Replace the second:

> ~~Only ambiguous submissions escalate to Tier 2. The thresholds τ_low and τ_high defining the ambiguous region are jointly tuned on a validation split to maximise overall F1-score subject to 2 constraints: escalation rate must not exceed 25%, and Tier 1 plagiarism precision must be at least 0.95.~~
>
> Only ambiguous submissions escalate to Tier 2. The thresholds τ_low and τ_high are jointly tuned on a validation split, subject to one hard constraint (overall system precision held at 1.000 — a false plagiarism accusation is treated as materially worse than a missed detection) and one objective (maximise F1 subject to that constraint). An initial design target of ≤25% escalation was not retained as a tuning constraint once validation showed it was incompatible with the precision requirement on this corpus; the deployed values are τ_low = 0.30, τ_high = 0.68, which measured 47.37% escalation on the test split — a real, reported deviation from the original design target, not a silent relaxation (see §3.5.3 and Chapter 4's discussion of Hypothesis 1).

### 3.4.3 Tier 2: Hybrid Semantic Detection — patch

Keep the first two sentences (embedding model, dimensionality). Replace the FAISS sentence:

> ~~Embeddings are stored in a FAISS (Johnson et al., 2021) IVFPQ index sized to fit within 16 GB RAM.~~
>
> Embeddings are stored in a FAISS (Johnson et al., 2021) index that automatically selects between two configurations by corpus size: exact search (`IndexFlatIP`) below 1,000 indexed vectors, and approximate search (`IndexIVFPQ`, parameterised in §3.6.4) above that threshold, trading exactness for scalability on larger deployments. Every corpus used in this thesis's evaluation remained under 1,000 vectors, so all reported Tier 2 results reflect exact search; the IVFPQ path is implemented and unit-tested but was not exercised by the reported evaluation.

Keep the third sentence (linear interpolation fusion) and adjust the last:

> Tier 2 returns a single similarity score plus the specific matched passage — the exact submission and source text spans behind the match, with character offsets on both sides — for the instructor-facing report.

### 3.4.4 Moodle Integration Layer — patch, plus one new paragraph

Keep the first sentence (event hooks, REST dispatch, gradebook rendering). Replace the async paragraph:

> ~~Detection runs asynchronously in a Celery background worker queue so student submission confirmation is never blocked. Cross-submission detection is supported by indexing each submission immediately on receipt, so subsequent submissions can be compared against everything already in the corpus.~~
>
> Detection runs asynchronously across two Celery worker pools so student submission confirmation is never blocked. Plagiarism detection (extraction, Tier 1/Tier 2 scoring, corpus indexing) runs on a strictly serialised worker, since these stages read and write shared, order-sensitive in-memory indices and a later submission's detection must not run ahead of an earlier submission's indexing. AI-authorship advisory scoring (§3.4.5) runs independently on a second, concurrent worker, since it shares no state with the detection pipeline and never gates submission completion. Cross-submission detection is supported by indexing each submission's fingerprint synchronously as a side effect of its own detection pass, and its lexical/semantic representations shortly afterward, so subsequent submissions can be compared against everything already indexed.

New paragraph, appended at the end of 3.4.4:

> Moodle's own scheduled-task scheduler has a fixed one-minute floor with no sub-minute resolution — a platform limitation, not a configuration choice. Relying on it alone for result delivery measured an end-to-end latency (submission to visible result) of up to several minutes. This was addressed with a self-requeuing ad-hoc task that polls the detection backend every 15 seconds after a submission is received, falling back to the original scheduled-task check only if that polling exhausts a bounded number of attempts — preserving a slower but guaranteed-eventual delivery path without depending on it for the common case. Measured end-to-end latency with this mechanism in place, via a complete live submission through the deployed Moodle instance, was approximately 20 seconds.

### 3.4.5 AI-Authorship Advisory Signal — new subsection, confirmed in scope

> A separate, independent signal estimates the likelihood that a submission was authored by a large language model, using a fine-tuned transformer classifier (§3.8) run against the full submission text. This signal is deliberately isolated from the plagiarism pipeline described in §3.4.1–§3.4.3: it is computed on a separate worker queue, stored in a separate database table, and never contributes to the plagiarism score or verdict. The isolation reflects a documented risk in the published literature: GPT-text detectors are reported to misclassify a substantial fraction of non-native-English writing as AI-generated, at rates several times higher than for native-English text. The system therefore surfaces this signal to instructors as an advisory indicator only, with an explicit disclaimer, never as an automated verdict.

---

## 3.5 Mathematical Model

### 3.5.2 Tier 1 Detection Function — replace

> The Tier 1 confidence score combines two normalised lexical signals asymmetrically:
>
> `c1(D) = max( containment(D, d*), min( norm(BM25(D, d*)), 0.6 ) )`
>
> where `d*` is the corpus document maximising each respective signal, and containment is defined in §3.6.1. BM25's contribution is capped at 0.6 — strictly below τ_high (§3.5.3) — so it can only ever route a submission to escalation, never independently resolve it as plagiarised.

### 3.5.3 Gating Decision Function — patch

Keep the routing logic (`route(D) = ...`) unchanged — it matches the deployed `gating.py` exactly. Replace the tuning sentence:

> ~~τ_low and τ_high are jointly tuned on the validation split under 2 constraints: escalation rate ≤ 25%, and TIER1_PLAGIARISED precision ≥ 0.95.~~
>
> The deployed values are τ_low = 0.30, τ_high = 0.68, selected on the validation split to maximise F1 subject to overall system precision remaining at 1.000. An escalation-rate ceiling of 25% was an initial design target (§3.4.2) but was not retained as a binding tuning constraint once validation showed the precision requirement could not be met within it on this corpus.

### 3.5.4 Tier 2 Hybrid Fusion — patch

Keep the formula unchanged (`c2(D) = α · S_dense(D, d*) + (1 − α) · norm(S_sparse(D, d*))`) — confirmed exact match to the deployed fusion. Add after the existing justification sentence:

> The deployed fusion weight is α = 0.6. `norm(S_sparse)` here is proportional scaling (§3.6.2), not per-query min-max normalisation — min-max was deliberately avoided because it rescales relative to whichever candidates happen to be in the local pool for a given query, which can inflate a weak match to a high score purely because nothing better was available in that specific comparison, independent of the match's true absolute similarity.

### 3.5.5 Cost Model

No change. This section's own stated worst-case bound (ρ ≤ 0.30, meaning ≥70% cost reduction) is exactly the target Chapter 4 reports against — keep as written.

---

## 3.6 Algorithms

### 3.6.1 Winnowing Fingerprinting — patch

Keep steps 1–3 unchanged (k=5, w=4, rolling hash, window minimum — all confirmed exact matches to the deployed configuration). Replace the similarity-measure sentence:

> ~~Similarity between 2 documents is the Jaccard coefficient |F(Dᵢ) ∩ F(Dⱼ)| / |F(Dᵢ) ∪ F(Dⱼ)|.~~
>
> Similarity between two documents is measured by containment, `|F(D) ∩ F(d*)| / |F(D)|`, rather than the symmetric Jaccard coefficient. Containment was adopted specifically because Jaccard collapses toward zero whenever the matched source document is substantially longer than the query — precisely the case of a short submission copying an excerpt from a longer reference document, which containment measures correctly as the fraction of the *query* that was reused, independent of how much longer the source is.

Keep the final sentence about the k+w−1 = 8-token minimum-detectable-match guarantee unchanged — still correct.

### 3.6.2 BM25 Sparse Retrieval — patch

Keep the BM25 formula, k1=1.5, b=0.75 unchanged — confirmed exact matches. Name the library precisely:

> Implemented via `BM25Plus` (rank-bm25 library).

Replace the tokenization sentence:

> ~~Stop words are stripped via SpaCy's standard English list. Lemmatisation merges inflected forms before indexing.~~
>
> Tokenization uses a lightweight regular-expression tokenizer (lowercasing, alphanumeric splitting) paired with a small, hand-curated English stopword list, avoiding a SpaCy dependency to keep the deployed service footprint smaller. No lemmatisation is applied — inflected forms are indexed as they appear.

Replace the normalization sentence:

> ~~The index is incremental: new submissions append to the inverted index without a full rebuild, supporting real-time cross-submission detection.~~
>
> Raw BM25 scores are converted to [0, 1] via proportional scaling — the raw score divided by a fixed saturation constant and capped at 1.0 — rather than per-query min-max normalisation, so that a weak match is never inflated to a high score merely because it was the best candidate available in one particular query's local pool. The index rebuilds incrementally as new submissions are added, supporting real-time cross-submission detection without a full reindex.

### 3.6.3 Dense Embedding Generation — patch

Keep the model sentence unchanged (all-MiniLM-L6-v2, 384-dimensional, confirmed exact). Replace the chunking sentence:

> ~~Each document is split into overlapping passages of 256 tokens with a 192-token stride, giving 25% overlap between adjacent passages.~~
>
> Each document is split into overlapping passages of up to 256 words with a 50-word overlap between adjacent passages (≈19.5% overlap), using a sentence-aware chunker that accumulates whole sentences up to the word budget rather than cutting at a fixed boundary, avoiding mid-sentence splits.

### 3.6.4 FAISS Approximate Nearest Neighbour Search — patch

Keep the parameter values (256 inverted lists, top-32 clusters scanned, top-50 candidates returned — all confirmed exact matches to the deployed configuration). Add a scoping note:

> This configuration governs the approximate-search (IndexIVFPQ) path described in §3.4.3, used above a 1,000-vector corpus size threshold; below that threshold, exact search is used and this configuration is not invoked. The recall/latency figures below characterise the approximate-search path specifically and were not re-measured against this thesis's own (smaller) evaluation corpora, which used exact search throughout.

### 3.6.5 Hybrid Fusion

Keep unchanged except the normalisation clause, which should match §3.6.2's correction: replace "min-max normalised" with "proportionally scaled" wherever it appears.

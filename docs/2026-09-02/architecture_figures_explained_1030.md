# Architecture figures, explained in full — accompanying prose for Figures 3.1 and 3.2

Written to sit directly under each figure in Chapter 3, stage by stage, with the reasoning behind each design choice included — not just what each stage does, but why it does it that way. Draws on the same verified facts as the §3.4–§3.6 corrections (`docs/2026-08-12/section_3_4_to_3_6_replacement_1430.md`) and Report 8's measured results.

---

## Figure 3.1 — Plagiarism-Detection Architecture, explained

### Overview

Every submission enters at a single point and passes through at most two tiers before resolving. The whole design is organised around one idea: most submissions are easy to classify with cheap, local, lexical checks, and only the genuinely ambiguous minority need the more expensive semantic analysis. This is what makes the system affordable to self-host — the architecture in Figure 3.1 exists specifically to avoid paying Tier 2's cost on every submission.

### Stage 1: Tier 1 — local lexical detection

Tier 1 runs two independent, complementary methods on every submission, with no external API calls and no per-submission cost.

**Winnowing** produces a document fingerprint: the text is stripped of whitespace and punctuation, broken into overlapping 5-character-gram sequences (k=5), each hashed with a rolling hash function, and a sliding window of size 4 (w=4) selects the minimum hash in each window as the fingerprint's representative hash. This guarantees that any shared substring of at least k+w−1 = 8 tokens between two documents will produce at least one matching hash, giving a formal detection guarantee rather than a heuristic one. The resulting similarity is measured by **containment** — the fraction of the *submission's own* fingerprint hashes found in a candidate source document — not the more common Jaccard coefficient. This distinction matters concretely: Jaccard is symmetric and penalises a match when one side is much longer than the other, which is exactly the case when a short submission copies an excerpt from a much longer reference document. Containment measures only "how much of what the submission contains was reused," independent of how much longer the source is, which is the actual question a plagiarism check needs answered.

**BM25** runs in parallel, ranking every document in the existing corpus by lexical relevance to the submission using the BM25+ scoring function (k1=1.5, b=0.75). Its raw score is converted to a [0,1] range by dividing by a fixed saturation constant, not by per-query min-max normalisation — a deliberate choice explained in the box below.

**Why cap BM25 at 0.6, and why take the maximum rather than a weighted average?** The two signals are combined as `c1 = max(containment, min(BM25_norm, 0.6))`. Winnowing detects direct textual reuse; BM25 detects lexical relevance, which can be high between two documents that are simply *about the same thing* without one having copied the other — two independent essays on the same set topic will share plenty of technical vocabulary. Capping BM25's contribution at 0.6, strictly below the plagiarism threshold (0.68) used in Stage 2, means lexical relevance alone can never be mistaken for a plagiarism verdict — a BM25-dominated match can, at most, push a submission into escalation for closer semantic examination, never resolve it as plagiarised on Tier 1's word alone. Winnowing's containment signal, because it measures actual substring reuse rather than general relevance, is the only signal allowed to resolve a plagiarism verdict without further checking.

*Box: why proportional scaling, not min-max normalisation.* An earlier design used per-query min-max normalisation, rescaling BM25 scores relative to whatever candidates happened to be in a given query's local pool. This has a specific, non-obvious failure mode: it inflates the single best-matching candidate to a score near 1.0 *purely because it was the best one available in that particular comparison*, regardless of the true strength of that match in absolute terms. A submission with only weak, coincidental lexical overlap to everything in the corpus would still have its best (weak) match rescaled to look strong. Proportional scaling — raw score divided by a fixed saturation constant, capped at 1.0 — preserves absolute magnitude instead: a genuinely weak match stays looking weak no matter what else is in the candidate pool that query.

### Stage 2: the gating decision

The combined score `c1` is compared against two thresholds, τ_low = 0.30 and τ_high = 0.68: below τ_low the submission resolves immediately as original; above τ_high it resolves immediately as plagiarised; in between, it escalates to Tier 2. These thresholds were tuned on a validation split with one hard constraint held throughout — overall system precision must stay at 1.000, since a false plagiarism accusation is treated as materially more costly than a missed detection — and the objective of maximising F1-score subject to that constraint. This is why the escalation band is as wide as it is: a narrower band was tested and found to violate the precision constraint. In measured practice, roughly 47% of submissions are ambiguous enough to require Tier 2; the other 53% resolve locally, at effectively zero marginal cost, in Tier 1 alone.

### Stage 3: Tier 2 — hybrid semantic detection

Only escalated submissions reach Tier 2, which augments the lexical signal with dense semantic similarity, able to recognise paraphrase and reworded plagiarism that shares little vocabulary with its source.

The submission is split into overlapping passages using a **sentence-aware chunker**: it accumulates whole sentences until adding the next one would exceed a 256-word budget, then starts a new chunk carrying over the last 50 words as overlap, so no chunk ever splits mid-sentence and no plagiarised passage near a chunk boundary is missed by both neighbouring chunks. Each chunk is encoded into a 384-dimensional vector using `all-MiniLM-L6-v2`, a compact sentence-transformer model chosen specifically because it sits within 2–3% of much larger models on standard semantic-similarity benchmarks while running comfortably on CPU — no GPU dependency, consistent with the system's affordability goal.

Two searches run against the existing corpus in parallel: a **dense search** via FAISS over the chunk embeddings (using exact search below roughly 1,000 indexed vectors, and an approximate IVFPQ index above that threshold, trading a small amount of exactness for scalability as the corpus grows), and a **sparse search** via the same BM25 index used in Tier 1. The two are fused by linear interpolation, `c2 = 0.6 · dense + 0.4 · sparse`, weighting the semantic signal more heavily but never discarding the lexical one entirely — a submission that scores well on both is stronger evidence than one that scores well on only one.

If `c2` exceeds 0.68, the submission resolves as plagiarised; the specific chunk pair behind the winning score is retained and used to construct the matched-passage evidence shown in the instructor report — the exact submitted text and exact source text behind the match, with character offsets on both sides, not just a similarity percentage.

### Stage 4: indexing and the corpus loop

Every resolved submission, regardless of which tier resolved it, is added to the shared corpus: its Winnowing fingerprint is inserted as a side effect of the Tier 1 query itself, and its BM25 text and dense embeddings are added immediately afterward. This is the entire mechanism behind cross-submission (peer-to-peer) detection — there is no separate "compare against other students" step; every future submission is simply checked against a corpus that, by construction, already contains everything submitted before it.

---

## Figure 3.2 — AI-Authorship Advisory Architecture, explained

### Overview

This pipeline answers a categorically different question from Figure 3.1 — not "did this text come from an existing source" but "does this text read like it was generated by a language model" — and its architecture makes that difference structural, not just conceptual. It shares no code path, no index, and no state with the plagiarism pipeline. This isolation is deliberate and is explained below, not incidental.

### Stage 1: classification

The submission's full text (up to a fixed token limit) is passed through a fine-tuned RoBERTa-family classifier (`Hello-SimpleAI/chatgpt-detector-roberta`), producing a raw score via softmax over its output classes — the probability mass assigned to the "AI-generated" class, a single number between 0 and 1. This model was selected specifically because it runs on CPU within a modest memory footprint, in line with the same affordability constraint that shaped every choice in Figure 3.1; more accurate zero-shot alternatives exist (Binoculars, in particular, is published state-of-the-art) but require two large language models resident in memory simultaneously, which does not fit the deployment hardware this system targets.

### Stage 2: verdict banding

Rather than a single pass/fail cutoff, the raw score is mapped to one of three verdicts: below 0.25, `likely_human`; above 0.75, `likely_ai`; the wide middle band, `uncertain`. This banding is deliberately conservative — it exists specifically so that a borderline score does not present itself to an instructor as a confident claim in either direction.

### Stage 3: independent storage and presentation

The result is written to its own database table, entirely separate from the plagiarism-detection results, and rendered in its own section of the instructor report with an explicit disclaimer. It never contributes to, blends with, or gates the plagiarism verdict or the submission's completion status in any way. This separation reflects a documented risk in the published literature that motivated the whole pipeline's advisory-only framing before this system was ever measured against real data: AI-text classifiers of this kind are known to misclassify a disproportionate share of writing by non-native English speakers, and more generally to generalise poorly to text generated by models unlike whatever they were trained on.

**This second risk was independently measured, not just cited.** Running the deployed classifier against 185 labelled items with known, verified authorship (95 genuinely human-written, 90 generated by GPT-3, GPT-4, or LLaMA) found precision of 0.882 — when the system does claim a submission is AI-generated, it is usually right — but recall of only 0.167: it misses the large majority (75 of 90) of genuinely AI-generated submissions, and most of those misses are confident, not landing in the cautious `uncertain` band at all. Recall varied sharply by generator: 29.4% for GPT-3-generated text, falling to 6.9% for GPT-4 — the model catches text most similar to its own training data far more often than text from a newer, different generator, exactly the generalisation weakness the architecture's isolation was designed to contain the consequences of. This is the empirical justification, not merely the stated intention, for why Figure 3.2 is drawn as a strictly one-way, advisory-only path with no route back into Figure 3.1's verdict: a signal this asymmetric (trustworthy when it fires, unreliable at catching what it's meant to catch) is unsuited to gating anything, and the architecture ensures it never does.

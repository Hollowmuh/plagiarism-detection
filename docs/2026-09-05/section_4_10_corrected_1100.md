# §4.10 — corrected replacement, ready to paste over the existing section

Replaces the entire existing §4.10 in `Chapter_4_Results_and_Discussion.docx`. Every claim below was independently verified against the actual source (not a search snippet) before inclusion — see `docs/2026-09-05` conversation history for the verification trail if anyone asks for it later. Changes from the original, stated plainly:

- **Removed entirely**: both Butakov citations (2013 "Procedia Computer Science" paper and 2009 "Computers & Education"/Crot paper) — neither could be confirmed to exist as described after checking two separate author bibliographies directly. The "Crot" Moodle plugin itself is real and Butakov is its real maintainer, but that does not establish that these two specific papers exist.
- **Removed**: the "40% cutoff" / "45–50% inflection point equilibrium" paragraph in the Arabzadeh subsection — confirmed not present in the actual paper.
- **Fixed**: Reducindo et al.'s page range (299–315, not 379–397) and removed the specific "$300–$1,000 per 100 students" figure, which could not be confirmed.
- **Removed**: Table 4.7's granular per-tool fractions (the "7/15," "13/15" style breakdown) — could not be confirmed against the source and are not reconstructable from what's publicly available.
- **Kept, unchanged**: the Weber-Wulff §4.10.2 material — every specific number checked (14 tools, the 01-Hum through 06-Para category codes, 42%/74% figures) was confirmed directly against the paper.
- **Softened**: the Sadasivan AUROC figure, since the specific ">0.95 to ~0.60" number could not be directly confirmed, though the paper's general finding (paraphrasing attacks degrade detector reliability, formalised via a distribution-distance bound) is real and confirmed.

---

## 4.10 External Empirical Validation and Benchmark Comparison

To evaluate whether the empirical findings reported in Sections 4.3 through 4.6 represent generalisable properties rather than idiosyncrasies of this specific codebase and dataset, this section benchmarks the results against published findings in two domains of external peer-reviewed literature: adaptive information retrieval, and AI-authorship detection benchmarking. A third domain — LMS-integrated plagiarism architecture — was investigated but is reported here only where a specific claim could be independently confirmed against its source; two candidate citations in this domain could not be verified and have been excluded rather than included on trust.

### 4.10.1 Validation of Dual-Tier Workload Partitioning (Arabzadeh, Yan & Clarke, 2021)

The core architectural premise of this thesis — that gating an efficient sparse retriever (Tier 1: BM25/Winnowing) into an expressive dense neural retriever (Tier 2: MiniLM/FAISS) can achieve near-dense accuracy at reduced cost — was independently investigated in information retrieval literature by Arabzadeh, Yan, and Clarke (2021), "Predicting Efficiency/Effectiveness Trade-offs for Dense vs. Sparse Retrieval Strategy Selection," in the Proceedings of the 30th ACM International Conference on Information & Knowledge Management (CIKM '21), pp. 2862–2866. Evaluating on the MS MARCO passage retrieval benchmark, Arabzadeh et al. tested a classifier-driven routing strategy between sparse retrieval (BM25, via the Anserini system) and dense retrieval (ANCE, with RepBERT and ColBERT for robustness checks).

**Gated routing can exceed always-dense retrieval on a fraction of the workload.** At a 50% hybrid budget — executing the more expensive strategy on only half of all queries — Arabzadeh et al.'s classifier-driven selection achieved a recall of 0.96, compared to 0.91 for a random 50% allocation, a confirmed improvement of over 0.05 (quoted directly from the paper). This is independent evidence for the same general principle this thesis's Experiment 2 result rests on (Table 4.2): a gated pipeline invoking the expensive tier selectively can outperform naive allocation of that same budget, because a fixed budget spent on the right queries carries more of the total benefit than the same budget spent uniformly.

**Latency**: Arabzadeh et al. report (citing Lin et al., 2020, within their own paper) BM25 query latency of 55ms versus ANCE dense-retrieval latency of 103ms, and separately note that their selective hybrid strategy achieves recall above 0.94 at a combined latency under 80ms. These are directionally consistent with this thesis's own measured latency profile (Table 4.2: local-only near-instant, dual-tier p50=21ms, cloud-only p50 in the tens of milliseconds range) — a gated approach recovering most of dense retrieval's effectiveness while paying a fraction of its latency cost is the same qualitative pattern in both systems, arrived at independently.

**Table 4.5: Comparison of dual-tier plagiarism detection with adaptive retrieval literature (Arabzadeh et al., CIKM 2021).**

| Evaluation dimension | Arabzadeh et al. (CIKM 2021), MS MARCO | This thesis, dual-tier system, test split (n=38) |
|---|---|---|
| Sparse baseline method | BM25 (Anserini) | Tier 1: BM25 + Winnowing fingerprints |
| Dense baseline method | ANCE (768-dim) | Tier 2: all-MiniLM-L6-v2 (384-dim, FAISS) |
| Selective/escalation budget | 50% allocated to the dense/hybrid strategy | 47.37% escalated to Tier 2 |
| Recall vs. a naive baseline at that budget | 0.96 (classifier-routed) vs. 0.91 (random allocation) | F1 0.884 (dual-tier) vs. 0.842 (always-Tier-2) |
| Reported latency | BM25: 55ms; dense: 103ms; selective hybrid: recall >0.94 at <80ms | Dual-tier: p50=21ms, p95=261ms, p99=351ms |

This thesis's own escalation rate (47.37%) is not claimed here to be independently predicted by Arabzadeh et al.'s results — their paper does not analyse an escalation-rate "equilibrium" or threshold, and no such claim is made. What is claimed, and is directly supported by their reported numbers, is the narrower, more defensible point: selective escalation of an expensive retrieval stage, on roughly half a workload, is independently documented elsewhere in the retrieval literature to outperform naive full-budget allocation of the same resource — the same structural argument this thesis's dual-tier design rests on.

### 4.10.2 Validation of AI-Authorship Detection Degradation and Governance (Weber-Wulff et al., 2023)

Experiment 4 (§4.6) measured 88.2% precision but only 16.7% recall for the deployed classifier, with recall decaying from 29.4% on GPT-3-generated text to 6.9% on GPT-4-generated text. This pattern, and the governance decision to treat AI detection as strictly advisory, is directly supported by the multi-institutional benchmark of Weber-Wulff, Anohina-Naumeca, Bjelobaba, Foltýnek, et al. (2023), "Testing of Detection Tools for AI-Generated Text," *International Journal for Educational Integrity*, 19:26.

Weber-Wulff et al. tested 14 detection tools (12 publicly available systems plus two commercial platforms, Turnitin and PlagiarismCheck) against six authorship categories: 01-Hum (human writing), 02-MT (human writing, machine-translated), 03-AI/04-AI (raw AI generation), 05-ManEd (AI text with human editing/patchwriting), and 06-Para (AI text with machine paraphrasing).

**Confirmed directly against the paper**: accuracy on raw AI-generated text (03-AI/04-AI) was 74%; on AI text with human editing (05-ManEd), accuracy fell to 42%, with roughly half of machine text going undetected once lightly edited. The paper's own conclusion is that detection tools are "neither accurate nor reliable," with a systematic bias toward classifying content as human-written — the same asymmetry (high precision, low recall) measured in this thesis's Experiment 4.

**Cross-generator degradation**: Sadasivan, Kumar, Balasubramanian, Wang, and Feizi, "Can AI-Generated Text be Reliably Detected?" (submitted to ICLR 2024; arXiv:2303.11156), provide a theoretical framework connecting detector reliability (AUROC) to the statistical distance between human and machine text distributions, and demonstrate empirically that paraphrasing attacks substantially degrade neural detector performance. This is consistent with, though not a precise numerical match to, this thesis's own measured cross-generator recall collapse (29.4% on GPT-3 down to 6.9% on GPT-4) — both findings point to the same underlying mechanism: detector reliability degrades as the text under test moves further from the detector's own training distribution.

**Governance implication**: Weber-Wulff et al.'s reported false-positive behaviour on human-authored text, and their explicit caution against using detection tools as the sole basis for a misconduct finding, independently supports the architectural decisions already described in §3.4.5 and §4.6.5 — a separate database table, a visually distinct advisory badge, an explicit disclaimer, and no path from this signal into any automated disciplinary action.

**Table 4.6: Accuracy by obfuscation category (Weber-Wulff et al., 2023) alongside this thesis's corresponding result.**

| Document category | Weber-Wulff et al. (2023), 14-tool average accuracy | Corresponding thesis result (§4.6) |
|---|---|---|
| 01-Hum: pure human-authored text | High accuracy; some tools still produced false accusations | Human false-positive rate = 2.1% (2/95) |
| 03-AI/04-AI: raw machine-generated text | 74% | GPT-3 detection recall = 29.4% (closest to the deployed classifier's training distribution) |
| 05-ManEd: AI text with human editing | 42% (~half undetected) | LLaMA detection recall = 11.1% |
| 06-Para: AI text with machine paraphrase | Substantially lower than raw AI text | GPT-4 detection recall = 6.9%; overall recall = 16.7% |

### 4.10.3 Validation of LMS Integration and Cost Considerations (Foltýnek et al., 2020; Reducindo et al., 2017)

**Usability and workflow compliance.** Foltýnek, Dlabolová, Anohina-Naumeca, Razı, Kravjar, Kamzola, Guerrero-Dib, Çelik, and Weber-Wulff (2020), "Testing of Support Tools for Plagiarism Detection," *International Journal of Educational Technology in Higher Education*, 17(1), 1–31, benchmarked 15 web-based text-matching systems across seven countries and eight languages against a usability evaluation covering more than 20 criteria. Their broad conclusion — that commercial plagiarism-detection tools frequently underperform on institutional workflow requirements (LMS integration quality, turnaround time, evidence presentation) — provides general external context for why a self-hosted, purpose-built Moodle integration (§3.4.4, §4.9.2) was chosen over adopting an existing commercial tool. This thesis does not reproduce Foltýnek et al.'s specific per-tool criterion scores, since a self-hosted single-system implementation is not directly comparable, tool-for-tool, to their 15-system benchmark on the same 20-plus-criterion rubric without re-running that rubric against this system specifically — a exercise outside this thesis's scope, noted here as a direction for future work (Chapter 5).

**Cost and openness.** Reducindo, Aceves-Pérez, Estrada-Esquivel, and Martínez-Enríquez (2017), "Integración de plataforma LMS y algoritmo de código abierto para detección y prevención de plagio en Educación Superior" ["Integration of an LMS platform and open-source algorithm for plagiarism detection and prevention in higher education"], *Revista General de Información y Documentación*, 27(2), 299–315, report on integrating an open-source plagiarism-detection algorithm directly into an LMS platform, motivated explicitly by the cost and data-sovereignty burden of commercial alternatives for resource-constrained institutions. This supports, in general terms, this thesis's own cost-accuracy result (§4.4): the dual-tier system's Tier 1 executes at $0.00 marginal cloud cost, with Tier 2 escalation costing $0.047 per 1,000 submissions — a similar motivation (open, self-hosted, low marginal cost) to the one Reducindo et al. document, though this thesis does not adopt their specific figures for commercial-tool pricing, which could not be independently confirmed and are omitted rather than asserted.

---

## Chapter Summary (§4.12) — one sentence to update

Replace: *"Fourth, benchmarking the system's integration against LMS architectural studies (Foltýnek et al., 2020; Butakov et al., 2013; Reducindo et al., 2017) demonstrates that decoupling compute-intensive detection into an asynchronous Celery/Redis service layer..."*

With: *"Fourth, benchmarking the system's integration against LMS architectural studies (Foltýnek et al., 2020; Reducindo et al., 2017) provides general external context for the value of a self-hosted, purpose-built integration over commercial alternatives, consistent with this thesis's own cost and workflow results; the asynchronous Celery/Redis service layer's own architectural justification rests on this thesis's own load-testing evidence (§4.9.3), not on an external citation for that specific mechanism."*

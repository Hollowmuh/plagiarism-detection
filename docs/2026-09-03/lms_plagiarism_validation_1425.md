# Integration Plan: LMS Plagiarism Detection Validation for Chapter 4

**Date:** 2026-09-03  
**Time:** 14:25  
**Target File:** `docs/2026-09-03/lms_plagiarism_validation_1425.md` and `Chapter_4_Results_and_Discussion.docx`

---

## 1. Objective

Add a dedicated validation subsection (**Section 4.10.3: Validation of LMS Plagiarism Detection Architectures**) to Chapter 4 of the thesis. This benchmarks the dual-tier system's Moodle integration, asynchronous task pipeline, cross-submission detection, and workflow usability against empirical findings from published LMS plagiarism detection literature:
1. **Foltýnek et al. (2020)** — *"Testing of support tools for plagiarism detection"*, *International Journal of Educational Technology in Higher Education*, 17(46).
2. **Butakov, Baidoo, & Parmar (2013)** — *"Implementation of service-oriented architecture for plagiarism detection in programming assignments"*, *Procedia Computer Science*, 23, 182-189.
3. **Butakov & Scherbinin (2009)** — *"The toolbox for local and global plagiarism detection"*, *Computers & Education*, 52(4), 781-788.
4. **Reducindo et al. (2017)** — *"Integración de plataforma LMS y algoritmo de código abierto para detección y prevención de plagio en Educación Superior"*, *Revista General de Información y Documentación*, 27(2), 379-397.

---

## 2. Verified Literature Findings and Alignment

### A. Foltýnek et al. (2020) — Moodle Integration Criteria & Usability Standards
- Evaluated 15 commercial and academic plagiarism tools on 23 usability and workflow criteria.
- **Key Empirical Criteria & Deficiencies in Existing Tools:**
  - Most commercial tools suffered from **lack of transparent institutional Moodle integration** (only 2 out of 15 fully satisfied all usability criteria).
  - **Turnaround Latency**: Commercial cloud tools exhibited turnaround times ranging from several minutes to hours during peak usage, with unpredictable queuing delays.
  - **Explainability & Result Presentation**: Highlighted passage comparison, side-by-side evidence rendering, and non-destructive report presentation were identified as non-negotiable instructor requirements that many tools failed to deliver cleanly.
- **Thesis Alignment**:
  - The dual-tier system fulfills the complete set of Foltýnek et al. workflow criteria: native Moodle event hooks, zero file renaming, gradebook badge rendering, highlighted passage matches (defect 9 corrected), and ad-hoc asynchronous delivery (~20s).

### B. Butakov et al. (2013) & Butakov & Scherbinin (2009) — Asynchronous Architecture & Local Privacy
- Butakov & Scherbinin (2009) established that local document fingerprinting inside the institutional perimeter avoids transferring student intellectual property to third parties, preserving privacy.
- Butakov et al. (2013) proved that embedding detection synchronously in the LMS PHP process causes severe performance degradation, timeouts, and request failures during student deadline spikes. They argued for an asynchronous Service-Oriented Architecture (SOA) with background message queues.
- **Thesis Alignment**:
  - Validates our deployment of FastAPI + Celery workers + Redis message broker, decoupling compute-heavy embedding and Winnowing tasks from Moodle's PHP web requests.
  - Validates load-test stability at 50 concurrent users (Section 4.9.3: zero dropped requests, p95 ~120 ms).

### C. Reducindo et al. (2017) — Cost Elimination in Higher Education LMS
- Demonstrated the economic necessity of open-source, locally integrated LMS plagiarism tools in university settings to eliminate recurring licensing fees ($300–$1,000 per 100 students).
- **Thesis Alignment**:
  - Directly validates our cost model (Section 3.5.5 and Table 4.2), where local Tier 1 analysis carries zero cloud cost ($0.00), and gated Tier 2 costs only $0.047 per 1,000 submissions.

---

## 3. Structural Additions to Chapter 4

1. **Insert Section 4.10.3: Validation of LMS Plagiarism Detection Architectures**:
   - Synthesizes findings from Foltýnek et al. (2020), Butakov et al. (2013), and Reducindo et al. (2017).
   - Adds **Table 4.7: Usability and LMS Integration Criteria Comparison (Foltýnek et al., 2020 vs. Dual-Tier Moodle Plugin)**.
2. **Re-number Subsequent Sections**:
   - Section 4.11: Summary of Hypothesis Outcomes (**Table 4.8**).
   - Section 4.12: Chapter Summary (synthesizing all 4 validation dimensions).
3. **Compile & Verify DOCX**:
   - Update `generate_chapter4.py` and run it.
   - Run `verify_chapter4.py` and `get_page_count.py` to confirm format and statistics.

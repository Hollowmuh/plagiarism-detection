# FAISS vector removal: migrate to `IndexIDMap2`

## Context

`docs/USER_GUIDE.md` currently documents "FAISS vectors are not removed on submission deletion" as an accepted, structural limitation. Re-reading the actual code while writing that section turned up something worse than what's documented: `purge_documents` (`backend/app/tasks/purge_tasks.py`) removes a deleted submission's entries from the Winnowing/BM25 indices but never touches `FAISSIndex._id_map`/`_doc_map`. Since `FAISSIndex.search()` (`backend/app/services/faiss_service.py:187-189`) resolves every hit back to a doc_id via `_id_map.get(int(idx))` with no existence check, a deleted submission's vector is not just inert — it is **actively returned as a live match candidate forever**, with a doc_id that no longer has a backing database row. This is a dangling-reference correctness bug, not just wasted compute, and it's worth fixing rather than leaving as documented debt.

The blocker today is that the index is built on raw `faiss.IndexFlatIP`/`faiss.IndexIVFPQ`, which have no vector-removal support at all — hence why `purge_documents`'s docstring says removal is impossible "without a full index rebuild." That's true of the raw index types, but `faiss.IndexIDMap2` is a thin wrapper that adds real `remove_ids()` support natively. Migrating to it closes the gap.

This plan was produced with two rounds of validation: an Explore pass read every real call site (`detection_pipeline.py`, `tier2_detector.py`, `embedding_tasks.py`, `purge_tasks.py`, `submissions.py`, and the (currently nonexistent) test coverage), and a Plan pass empirically tested the actual FAISS API (`faiss-cpu==1.13.2`, matching `requirements.txt`) against a live Python session rather than trusting memory — it surfaced a real production race condition (below) that the original design would have introduced.

## Key design decisions

1. **Wrap both Flat and IVFPQ paths in `IndexIDMap2`.** Confirmed empirically: bare `IndexFlatIP.add_with_ids()` raises `RuntimeError` — wrapping is mandatory for the Flat path. `IndexIVFPQ` natively supports `add_with_ids`/`remove_ids` without wrapping, but wrapping it too keeps `self._index` uniformly `IndexIDMap2` everywhere, which simplifies the legacy-detection check in `_try_load()` to one `isinstance` test regardless of backend.

2. **Chunk-aware removal.** `tier2_detector.index_chunks()` (`backend/app/services/tier2_detector.py:165-186`) fans one submission's `doc_id` out into N FAISS entries keyed `f"{doc_id}__chunk_{i}"` — unlike the Winnowing/BM25 indices, which are one-entry-per-submission. Confirmed via `indexing_tasks.py`/`submissions.py` that `purge_documents` only ever receives the base `Document.id` string, never chunk suffixes. So the new removal method must match by prefix (`doc_id` or `doc_id + "__chunk_"`), not exact key — a naive exact-match `remove()` would silently leave every chunk's vector behind, missing the actual bug this change exists to fix.

3. **Explicit, persisted `_next_id` instead of deriving it from `ntotal`.** After removals, `ntotal` is legitimately less than the highest id ever assigned; reusing a lower `_next_id` risks a future `add()` colliding with an id still alive in `_id_map` for a different doc. Persist `_next_id` in the `.meta.json` sidecar going forward, with a fallback to `ntotal` for meta.json files written before this change.

4. **In-process auto-migration on load — but memory-only, no eager save.** The original design (auto-migrate legacy files on `_try_load()`, then immediately `save()` once) has a real bug: `celery_app.py:68-69`'s `@worker_ready.connect` hook calls `get_faiss_index()` on **every** worker process at startup, including `celery-worker-fast` — which today never calls `.save()` on anything (confirmed: `.save()` on the FAISS index is called from exactly one place in the whole codebase). An eager save-on-migrate would make both `celery-worker` and `celery-worker-fast` race to independently save the same file on the next restart, with `celery-worker-fast` risking clobbering vectors `celery-worker` adds in between. **Fix: migrate in memory only; let persistence happen naturally at the next real write** (the existing every-100-vectors check in `index_document()`, or the new unconditional save added to `purge_documents`). This preserves today's invariant that only `celery-worker` ever writes the file, at zero extra cost (re-migrating in memory on every restart until the first real write is cheap — IVFPQ is confirmed unreachable in practice, see below, and Flat reconstruction is fast).

5. **`upgrade_to_ivfpq()` is dead code today** (grepped: nothing calls it, no celery-beat schedule exists at all) — the live VM's index has certainly never become IVFPQ. Still implement and unit-test that migration branch correctly for correctness, but the live-VM verification only needs to exercise the Flat path.

6. **Defensive skip on `_id_map`/`ntotal` mismatch.** `save()` today writes the `.faiss` file and `.meta.json` non-atomically; a crash between the two writes could leave a `_id_map` shorter than `ntotal` on a currently-legacy file. If `len(_id_map) != ntotal` at migration time, skip migration and log a warning (same pattern as the existing `faiss_meta_missing` case) rather than reconstructing a mismatched mapping. Also harden `save()` itself to write-to-`.tmp`-then-`os.replace()` for both files while touching this code, since the migration path increases how often `save()`'s non-atomicity window gets exercised in practice.

## Changes

### `backend/app/services/faiss_service.py`

- `_ensure_index()`: `self._index = faiss.IndexIDMap2(faiss.IndexFlatIP(self.dimension))`.
- `add()`/`add_batch()`: switch to `.add_with_ids(vec_or_vecs, np.array(fids, dtype=np.int64))`. Change `self._vectors` from `list[np.ndarray]` to `dict[int, np.ndarray]` keyed by fid (needed so removal can evict from it, and so `upgrade_to_ivfpq()`'s retrain step stays correct after gaps exist instead of relying on positional coincidence).
- `search()`: no change — `IndexIDMap2.search()` already returns external ids (confirmed empirically), and `_id_map.get(int(idx))` already degrades gracefully for a missing/stale id.
- New `remove_document(self, doc_id: str) -> int`: find all `_doc_map` keys equal to `doc_id` or prefixed `f"{doc_id}__chunk_"`; if none, return `0`; else `remove_ids(IDSelectorBatch(np.array(fids, dtype=np.int64)))`, delete each from `_id_map`/`_doc_map`/`_vectors`, return count removed. No-ops safely (mirrors `FingerprintIndex.remove()`/`BM25Index.remove()`'s existing no-op-on-missing behavior used in `purge_tasks.py` today).
- `_try_load()`: persist/restore `_next_id` explicitly via meta.json (fallback to `ntotal` if absent). After load, if `not isinstance(self._index, IndexIDMap2)`: check `len(_id_map) == ntotal` (else skip + warn per decision 6); else reconstruct every vector (`reconstruct_n(0, ntotal)`, calling `make_direct_map()` first if IVFPQ — confirmed this only works because legacy ids are sequential 0-based), build a fresh `IndexIDMap2`-wrapped index, `add_with_ids` using the existing `_id_map` keys (preserves every doc_id↔id association exactly), set `_next_id = max(keys)+1`, populate `_vectors`. **No `save()` call** (decision 4). Wrap in try/except — on failure, log and leave the index as the original unwrapped object; `remove_document()` checks `isinstance` and no-ops with a log line rather than crashing if called against a not-yet-migrated index.
- `save()`: add `"next_id": self._next_id` to the meta.json payload; write both files to `.tmp` then `os.replace()`.
- `upgrade_to_ivfpq()`: build `ids`/`training_data` from one ordered pass over `self._vectors.items()`. Set `ivfpq.nprobe = self.nprobe` on the **raw** IVFPQ object before wrapping (confirmed `IndexIDMap2` doesn't expose `nprobe` as a settable attribute on the wrapper — must be set on the underlying index first, and it persists correctly through the wrap). Then wrap and `add_with_ids`.

### `backend/app/tasks/purge_tasks.py`

- Import and call `get_faiss_index().remove_document(doc_id)` per doc_id, alongside the existing fingerprint/BM25 removal.
- Call `faiss_idx.save()` once after the loop (purge is low-volume; unconditional save is fine).
- Update return dict to `{"purged": len(doc_ids), "faiss_vectors_removed": faiss_removed}` — already confirmed the caller (`submissions.py:280`) uses `.delay()` fire-and-forget and never inspects the return value, so this is safe to change.
- Update the docstring — the "FAISS vectors are intentionally NOT purged" paragraph is no longer accurate.

## Tests

New `backend/tests/test_faiss_service.py` (direct-call style, real objects, no mocks — matching `test_purge_tasks.py`'s existing pattern; use `FAISSIndex(index_path=str(tmp_path / "test.faiss"))` for isolated save/reload cycles):
1. Add/search round-trip; `add_batch` skips existing doc_ids.
2. `remove_document` removes an exact (non-chunked) doc_id.
3. `remove_document` removes **all** chunk entries for a base doc_id (`__chunk_0/1/2`).
4. `remove_document` does not affect a different doc_id that shares a prefix (e.g. `"a"` vs `"a2"`) — regression test for the prefix-matching logic.
5. Removing a nonexistent doc_id is a no-op returning `0`.
6. **The actual bug fix, directly**: add → search (present) → remove → search again with the same query vector → removed doc_id is absent from results (not just that `total_vectors` dropped).
7. Save-and-reload preserves ids and removals across a fresh `FAISSIndex` instance.
8. After reload with a gap (add 3, remove 1, save, reload, add new) — new id is never a reused/colliding id.
9. **Legacy-format migration**: hand-construct a bare `IndexFlatIP` + matching sequential-id meta.json (simulating a pre-this-change file), load it via `FAISSIndex`, assert it's now `IndexIDMap2`-backed, all doc_ids still searchable, and `remove_document()` now actually works against it.
10. Legacy IVFPQ migration (small synthetic `nlist=1` index) — same shape as #9, verifying `make_direct_map()` + `reconstruct_n` + rewrap.
11. **Migration is memory-only**: construct from a legacy file, assert the on-disk file is byte-unchanged immediately after construction, then call `.save()` explicitly and confirm it now round-trips as `IndexIDMap2`. This pins decision 4 as a regression test so it can't regress back to eager-save without the race being reintroduced silently.
12. Migration is skipped (no exception, index stays unwrapped, warning logged) when `_id_map`/`ntotal` disagree.

Extend `backend/tests/test_purge_tasks.py`:
13. New test indexing real FAISS chunk entries (via `get_faiss_index().add_batch()` with `__chunk_N` keys, alongside the existing fingerprint/BM25 setup), then asserting `purge_documents.run([doc_id])` removes them from FAISS search results too.
14. Extend the existing multi-doc test with the same FAISS assertion (matches the real call shape — `submissions.py` always calls with a list).

## Verification against the deployed VM

1. Before deploying: confirm the live index's actual current type/size (`docker compose exec celery-worker python -c "import faiss; idx=faiss.read_index('/data/faiss/index.faiss'); print(type(idx).__name__, idx.ntotal)"`) — expected to print `IndexFlatIP` given `upgrade_to_ivfpq()` is unreachable. Snapshot an md5sum of the `.faiss`/`.meta.json` pair and back up the `.faiss` file (`cp index.faiss index.faiss.pre-migration.bak`) as a cheap, non-mandatory safety net (full DR path exists regardless: `Document.extracted_text`/`DocumentChunk.chunk_text` are persisted in Postgres, so the vector store is rebuildable from source of truth if ever needed).
2. Deploy, tail logs across both `celery-worker` and `celery-worker-fast` at startup, confirm `faiss_loaded` followed by a migration log line with no `faiss_migration_failed`.
3. Confirm no premature write: md5sum of `.faiss` unchanged immediately after startup (proves decision 4's "no eager save" held).
4. Force a real write (submit one test document, or run `purge_documents.run([...])` against a disposable test doc_id inside the container) and confirm the file's mtime changes and now loads back as `IndexIDMap2`.
5. End-to-end functional proof of the actual fix: pick a real indexed submission's doc_id, delete it via the normal API path (triggers `purge_documents.delay(...)`), then confirm from inside the container that `FAISSIndex().search()` using that submission's own former text no longer returns its doc_id.
6. Run the new/updated unit test suite (`pytest backend/tests/test_faiss_service.py backend/tests/test_purge_tasks.py`) before deploying, as the primary gate — VM verification is confirming the same behavior holds against real persisted state, not a substitute for it.

## Docs to update after this lands

- `docs/USER_GUIDE.md` §6 and §9 — the "FAISS vectors are not removed on submission deletion" limitation becomes fixed; replace with a short note that removal is now supported via `IndexIDMap2`.
- `evaluation/reports/07_full_pipeline_audit.md` and `evaluation/reports/04_exp3_threshold_sensitivity.md` (wherever the FAISS-purge limitation is currently documented) — add a dated follow-up addendum in this repo's established style, rather than editing the original finding away.

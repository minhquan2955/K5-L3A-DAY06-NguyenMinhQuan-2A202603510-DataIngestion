# Day 06 pipeline implementation plan

Goal: finish the existing TODO contracts and verify them before running any lab retrieval evaluation.

Spec: repository GUIDE.md, BENCHMARK.md, benchmark/README.md and the existing models.py contracts.

Architecture: retain the Python modules, dataclasses, psycopg and pypdf already installed. Use exact pgvector cosine search and parameterized SQL. Keep preparation, ingestion and dev/test evaluation as explicit CLI modes.

Constraints: preserve user edits, source snapshot and question splits; work in the current starter/src workspace; do not run lab eval or upload the corpus while implementing. No extra dependencies, automatic commits or branch changes.

Review focus: font-specific PDF ligatures and page offsets; chunk boundary coverage and stable IDs; transactional stale-chunk replacement without deleting other documents; metadata filter parameterization and vector dimensions; no gold leakage or automatic human labels; frozen input/config checks before test.

- [x] Ingestion and chunking. Write tests for Unicode/paragraphs, empty pages, real manifest/evidence consistency, invalid sizes, paragraph boundaries and stable chunk IDs. Implement load_pdf, normalize_text, fixed_size and by_paragraph. Verify with unittest.
- [x] Evidence evaluation. Test wrong source/page, incomplete evidence, alternative gold, top-3 limits and separate strategy/split denominators. Implement evaluate_query and summarize without deriving human audit labels.
- [x] PostgreSQL storage. Test against an isolated temporary table with small synthetic vectors: cosine ranking, filter isolation, repeat ingestion, changed/empty document cleanup, rejected dimensions and transaction rollback. Implement schema, upsert, search and count using existing psycopg.
- [x] Orchestration. Implement frozen-input validation and CLI modes prepare/ingest/eval. Prepare A/B/C with B/C sharing chunks. Batch real embeddings, preserve model/config, select on dev before test, write traces/statistics and blank audit templates. Test preparation without API/eval and invalid freeze/config rejection.
- [x] Finish. Repair renamed manifest references while preserving its digest; document commands. Run the complete suite, a local prepare-only check, pip check and diff check. Request an independent code review and address material findings. Leave actual ingest and lab eval unrun.

Verification command from starter/src: `.venv/Scripts/python.exe -m unittest discover -v`.

Progress and evidence will be recorded below as each task finishes.


Completed verification:
- 21/21 unittest checks passed, including real pgvector transactions on disposable test tables.
- CLI prepare checked 58 content pages, A=449 chunks and B=C=505 chunks, 30 blank coherence samples, and byte-identical B/C chunk exports. Temporary outputs were cleaned automatically.
- All normalized page counts and 21 gold evidence passages match the frozen inputs. No lab retrieval evaluation or corpus API upload was run.
- pip check and git diff --check passed. Database setup check prints Setup OK.
- Manifest rename was repaired in benchmark README/freeze only after verifying its original digest was unchanged.

Independent review and fixes:
- Preserved matching coherence labels and refused overwrite of existing eval reports; regression verified RED to GREEN.
- Bound run/index/dev selection to full chunk fingerprints, including a same-count changed-content regression.
- Kept filter-compliance labels blank for every strategy when the question requests a filter; requested/applied filters are both recorded.
- Corrected midpoint-whitespace audit selection and inferred source blocks for PDFs without paragraph separators; regression verified RED to GREEN.

Review boundaries:
- Live PostgreSQL behavior was verified by the main agent. API setup had succeeded earlier; corpus batching was verified with a synthetic provider boundary, not a corpus upload.
- Human grounding/metadata/coherence labels remain blank. Source-line paragraph inference is a documented heuristic whose semantic quality still needs manual audit.
- One writer is expected for this lab. Concurrent writers, manual database corruption and large-scale performance tuning are outside the implementation scope.
- No commits, merges, branch changes or additional dependencies were introduced in this implementation task.

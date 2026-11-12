# ClinVar verification: sgRNA-1617 / SITE-006 / MBOAT1

Validated November 12, 2026 using live Ensembl and NCBI E-utilities responses.
The supplied guide name `shRNA-1617` corresponds to `sgRNA-1617` in the seed file.

- Off-target interval: GRCh38 chr6:20,203,311–20,203,333 (1-based inclusive).
- Ensembl gene: MBOAT1, ENSG00000172197, chr6:20,099,684–20,212,780.
- Both intervals use the same assembly, chromosome, and coordinate convention.
- All 13 gene-search matches were retrieved and examined; results were not truncated.

| Verification outcome | Count |
|---|---:|
| Excluded: clinical classification | 0 |
| Excluded: missing usable GRCh38 coordinates in ESummary | 10 |
| Excluded: missing Ensembl gene boundaries | 0 |
| Excluded: outside Ensembl gene interval | 0 |
| Directly overlapping variants | 3 |
| Verified variants elsewhere in the gene | 0 |
| Total examined | 13 |

The original zero verified-elsewhere count was reproduced. Missing gene boundaries
were not the cause. Ten records had no usable explicitly GRCh38 locations in the
ESummary fields inspected by the dashboard. The three remaining records overlapped
the off-target interval and therefore belong to the direct-overlap category.

The three qualifying direct overlaps are large copy-number variants:

| ClinVar record | Type | GRCh38 interval |
|---|---|---|
| [4755369](https://www.ncbi.nlm.nih.gov/clinvar/variation/4755369/) | Copy number loss | chr6:12,020,008–22,846,454 |
| [155430](https://www.ncbi.nlm.nih.gov/clinvar/variation/155430/) | Copy number gain | chr6:156,974–46,789,291 |
| [150044](https://www.ncbi.nlm.nih.gov/clinvar/variation/150044/) | Copy number gain | chr6:3,224,310–30,657,190 |

The ten missing-GRCh38 outcomes were Variation IDs 1810398, 1809386, 688193,
687409, 563140, 560067, 443497, 443496, 442457, and 253526. This describes the
returned summaries, not proof that no GRCh38 mapping could exist elsewhere.

## Validation and limits

All 34 selected automated tests passed, including 11 new tests for outcome
assignment, count reconciliation, interval boundaries, classification filtering,
truncation, unavailable gene boundaries, request failures, and debug visibility.
The running dashboard reproduced the 13/10/3/0 breakdown, automatically opened
Site Analysis after Analyze, and hid per-record details with debug disabled.

The independent genomic-region ClinVar search returned zero verified overlaps
for this site during validation, while the gene search found the three overlaps
above. The interface labels these as separate searches. A region-search zero
is not evidence that no overlapping records exist in ClinVar.

These are interval overlaps with existing clinical records, not predictions that
CRISPR would create these copy-number changes. Strict classification filtering,
the 100-record cap, and GRCh38-only verification remain in effect. No liftover
or alternative coordinate retrieval was introduced. Live records may change.

## Files changed

- `services/clinvar.py`: exclusive outcome counters and record audit trail,
  valid gene-interval handling, retrieval/truncation metadata, reconciliation.
- `services/annotations.py`: pass missing boundaries through for explicit
  unavailable verification instead of failing before the query starts.
- `ui/analysis_results.py`: verification counts, debug-only record details,
  precise zero/truncation messages, and search-source clarification.
- `app.py`: version the annotation cache key to avoid reusing older snapshots
  that lack verification outcomes.
- `tests/test_clinvar_verification_outcomes.py`: focused mocked tests.
- This validation report.

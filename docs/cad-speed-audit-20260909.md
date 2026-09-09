# CAD replacement speed audit

Goal: reduce fresh end-to-end translation time by 50% with equal or better
translation completeness, accuracy and layout. This goal is not yet verified.

## Implemented

- Parse each page into one display list for review rendering; retain all source
  and target crops, including preserved and dismissed records.
- Separate layout proposals for distinct fields in shared CAD cells. Overlapping
  OCR fragments remain subject to contextual review rather than automatic merging.
- Compare painted image digests and transforms instead of PDF resource counts.
  Legacy jobs obtain image evidence from their hash-bound source. Lost/moved
  images still fail; unused resource cleanup does not require dummy objects.
- Replace workflow guidance with clause-level reconciliation before translation,
  preserved numbering/constraints and batch repair. Rebuild corrections through
  the packet; do not edit evidence hashes to accommodate external PDF mutations.

## Deferred after review

- Universal 8.5 pt or factor-of-two font reduction: not established by OCR data;
  one repaired drawing is insufficient evidence for a general sizing rule.
- Automatic collapse of technical requirements: risks lost clause structure and
  constraints. Use full context but preserve each numbered clause and its content.
- Removing preserved/dismissed review records: could hide incorrect dispositions.
- Removing structural verification: replace resource counting with content and
  placement evidence instead.

## Measurements

Input: the existing rotary-kiln job, one page, 200 review records. Compare HEAD's
cad_batch.py with the working version in separate cold output directories. No
translation was rerun. OCR caches were empty for both complete-review runs.

| Operation | Before | After | Reduction |
| --- | ---: | ---: | ---: |
| Review rendering without residual OCR | 14.782 s | 1.425 s | 90.4% |
| Complete review with residual OCR | 35.058 s | 20.290 s | 42.1% |

All 402 corresponding review PNGs have identical decoded pixels. Both full
reviews retain 200 records and return the same empty residual-candidate list.
These are single-run component benchmarks, not end-to-end translation gains.
Artifacts: tmp/cad-speed-audit/benchmark.json and full-review-benchmark.json.

Validation: 53 CAD/PDF routing tests pass; shared horizontal/vertical fields,
lost/moved images and pixel-equivalent display-list crops have regression tests.
Real source fields o00007/o00013 and o00024/o00031 now have disjoint proposals.

Next fresh translation should record first candidate, repair rounds and delivery
time. Do not treat filesystem-time gaps as isolated translator or repair CPU
time. The earlier 12–18 minute prediction was unmeasured and is withdrawn.

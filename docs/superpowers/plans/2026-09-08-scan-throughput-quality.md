# Scan throughput and quality implementation plan

**Goal:** Target a complete 38-page scan translation within 3600 seconds, with
source graphics, page context and independent semantic review retained.

**Scope:** Existing scan adapter only. Preserve the pre-existing detector and
OCR deduplication edits. No new translation dependency or automatic passing reviews.

**Design:** Checkpoint OCR by source/page/config/render hash. Reduce background
sampling to the actual six-pixel boundary; cache cleaned raster bases by all
pixel-affecting inputs. Keep official text generation and final checks. Export
ordered page context and require an explicit semantic-review record at delivery.

- [x] Add failing tests for bounded sampling, cache invalidation, OCR resumption,
  ordered context and missing/stale/incomplete semantic reviews.
- [x] Implement and test each change within the existing scripts.
- [x] Benchmark the existing 38-page job and representative cold OCR pages;
  report measured stages separately from projected end-to-end time.
- [x] Update scan instructions; run all adapter regression tests and diff checks.

Do not claim the one-hour end-to-end target is verified by warm-cache builds,
mocked OCR or by reusing the old machine translations. A fresh complete run
including actual semantic review is required for that acceptance claim.

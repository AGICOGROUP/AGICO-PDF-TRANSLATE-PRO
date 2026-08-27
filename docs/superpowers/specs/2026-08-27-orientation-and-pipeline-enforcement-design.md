# PDF translation orientation and pipeline enforcement design

## Objective

Eliminate two failure classes without adding more than 30 seconds of routine
processing overhead per document:

1. target text direction differs from the visible source-text direction;
2. an agent bypasses the adapter workflow, produces a partial summary, or
   delivers without complete coverage and official final QA.

The four independent adapters remain isolated: native PDF, scan PDF,
standalone image, and bilingual overlay. Each adapter owns its checks at the
tail of its own workflow.

## Constraints

- Reuse existing OCR, render, geometry, and manifest data.
- Do not add another OCR pass or another full-document render.
- Keep current gate counts; add or replace internal assertions only.
- Expected added routine cost is at most 30 seconds per document.
- Engineering drawings remain Chinese plus one foreign language by default.
- A companion panel must be a complete mapping, never a summary substitute.

## Phase 1: Orientation correctness

### Scan PDF

- Detect visible text orientation from existing OCR boxes/results even when the
  PDF page `/Rotate` value is zero.
- Store `rotation` as one of 0, 90, 180, or 270 on each source line and block.
- Require every translated block to inherit or explicitly justify the source
  rotation.
- Make `build_scan.py` render the target block using that rotation.
- Add `orientation_mismatch_failures` to the scan adapter's existing layout
  gate and final report.
- Improve drawing routing for image-internal rotation and drawing evidence.

### Native PDF

- Audit native text matrices and embedded image OCR orientation.
- Preserve source text-matrix direction for native replacement blocks.
- Apply the scan-style block rotation rule only to modified embedded-image
  labels.

### Standalone image

- Reuse raster orientation evidence from the image adapter's extraction data.
- Require target raster text direction to match the corresponding source
  direction before unwrapping the intermediate PDF.

### Bilingual overlay

- Derive overlay rotation from the source block rather than assuming horizontal
  text.
- Validate source/target direction pairing before delivery.

## Phase 2: Enforce complete official execution

### Required provenance

Every adapter must emit an adapter-owned provenance record containing:

- immutable source SHA-256;
- adapter name and version;
- manifest SHA-256;
- official builder report SHA-256;
- final candidate SHA-256;
- official verifier report SHA-256 and `passed: true`.

The delivery check rejects a candidate without this chain. An ad-hoc script may
create diagnostics, but its PDF cannot be delivered as the adapter's result.

### Coverage enforcement

- Every clear source label receives a stable source ID.
- Every source ID is assigned exactly once to translated, bilingual-complete,
  or preserve-confirm status.
- Preserve-confirm requires a supported reason and cannot cover readable
  informational text.
- Companion panels contain a one-to-one mapping for every assigned source
  label; a condensed summary fails coverage.
- Final reports include zero unassigned source lines and zero untranslated clear
  labels.

### Adapter isolation

- Native, scan, image, and bilingual adapters do not call another adapter's
  final gate set.
- Shared low-level utilities are allowed, but each adapter emits and verifies
  its own provenance and final report.

## Testing sequence

Implement one adapter at a time using red-green-refactor:

1. Scan: rotated-content fixture, incomplete companion panel, and ad-hoc output
   rejection.
2. Native: rotated native text and rotated embedded-image label fixtures.
3. Image: rotated raster label and missing provenance fixtures.
4. Bilingual: rotated overlay and incomplete source/target pairing fixtures.
5. Run each adapter's regression suite, then the repository-wide suite.
6. Synchronize project and installed skills only after all relevant tests pass.

## Success criteria

- The `1002-0204-03.pdf` fixture routes as an engineering drawing.
- Its Chinese overlay follows the drawing's visible reading direction.
- Every clear non-numeric label is translated or explicitly preserved.
- A summary-only companion panel fails.
- A PDF produced outside the official adapter build/verify chain fails delivery.
- Existing quality checks remain intact and routine added processing stays
  within the accepted 30-second budget.

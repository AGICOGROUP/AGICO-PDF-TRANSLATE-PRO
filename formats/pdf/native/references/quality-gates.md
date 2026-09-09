# Native/mixed PDF acceptance

Apply [the shared delivery policy](../../../../references/delivery-policy.md).
Only incorrect content, incomplete/unreadable output or damage to key structure
blocks completed delivery. Selectability, geometry and image checks provide
evidence for these requirements; source-relative typography is diagnostic.

Review every page in context using the original and target content. Save actual
findings in translation-review.json. Never infer semantic accuracy from counts.
Retain source/candidate hashes and traceable evidence for unchanged pages.

Render all pages for initial coverage; after correction render only affected
pages. Reuse unchanged extraction, OCR and clean bases. Do not invoke another
adapter's full gate set. Check modified image regions for actual damage.

Final verified delivery may carry cosmetic warnings. At the time limit provide
a clearly labelled preview if final requirements remain unverified or failed;
retain the true stage and reports and list known issues.

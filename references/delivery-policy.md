# Translation acceptance and time budget

All PDF/image adapters use three blocking requirements:

1. Content correct: preserve meaning, conditions, negation, numbers, units and
   identifiers. No omitted, duplicated, invented or untranslated readable prose.
2. Complete and readable: no missing pages, square glyphs, obscured paragraphs
   or meaningful clipping. Preserve required selectable/copyable target text.
3. Key structure intact: preserve page geometry, table relationships, drawing
   connections, images, symbols, signatures and seals.

Source-relative font floors, exact header/footer size, minor weight/alignment
differences and harmless bounding-box intersections are diagnostic warnings.
Inspect suspicious regions once; confirmed unreadability or semantic/structural
damage is blocking. Do not rebuild solely to eliminate cosmetic warnings.
Do not relabel real content as OCR noise, replace it with dots or fabricate
passing reviews. Missing evidence is unverified, never zero failures.

Target 120 seconds per selected scan page or standalone image end to end;
over 120 through 180 seconds is acceptable, over 180 seconds fails speed
acceptance. Keep the 120-second optimization target; 180 seconds is the ceiling,
not the desired runtime. For 10 scan pages, target 20 minutes with a 30-minute
ceiling; also report individual page overruns rather than hiding them in an average.
Include instruction reading, extraction, translation, layout, review, export
and any dispatch/return/final handoff. Executor/subprocess duration alone is not
the user's complete waiting time. Report it separately, with the full task-entry
and handoff timestamps; do not infer full-service stability from worker-only runs. Apply
the same budget to scan-dominated pages in mixed jobs. Count active wall time
from task start, excluding explicit user pauses. Check time at stage boundaries
and warn early when representative pages predict an overrun.

Within the same run or an authorized non-test resumption, reuse source-bound
OCR, translations, clean bases and reviews. Tests use new directories and fresh
extraction/translation/review, never historical task artifacts. Start with one
adequate-resolution OCR pass; retry only uncertain/missed regions at higher
resolution. Render all pages for initial coverage, then only affected pages.
Reuse unchanged page evidence by content identity and bind the assembled PDF to
current evidence. If the builder requires full assembly, avoid repeating full
OCR and review. Do not redesign the pipeline during a document job.

At the time limit stop automatic repair loops. Deliver a completed translation
when all three requirements pass, retaining warnings. Otherwise provide the
latest readable candidate explicitly named/described as a preview, listing
known defects and unverified items. Keep its real failed/unverified state; never
set verified/passed for a preview. If no readable candidate exists, report that.

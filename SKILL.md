---
name: PDF-TRANSLATE-PRO
description: Use when translating PDFs or static PNG/JPEG images whose professional meaning, page layout, tables, graphics and selectable target text must be preserved.
---

# PDF-TRANSLATE-PRO

This repository supports PDF, PNG, JPG, and JPEG inputs.

For every adapter, follow the cement terminology guidance in
`references/page-context-translation-review.md` when relevant terms occur.
Use the bundled user-revised table, including for drawing labels and image text.

Read `references/delivery-policy.md` for the three blocking requirements,
nonblocking cosmetic diagnostics, incremental review and the 120-second target /
180-second ceiling per scan page or image. Apply this policy in the selected adapter.

Choose exactly one adapter from the actual file format:

- PDF: read `formats/pdf/SKILL.md` completely and use its content-based router.
- Static PNG or JPEG image: read and follow `formats/image/SKILL.md`.

Reject unsupported formats, animated images, and multi-page image containers. Never merge adapter workflows. File format selects the top-level adapter; PDF content inspection selects the PDF sub-adapter.

Output mode follows the user's requested result, for every target language:

- “翻译为英文/中文”, “翻译成英文/中文”, “英文版/中文版” or another single
  target-language translation means `replace`: replace the source-language text
  with the target language, including on engineering drawings.
- “加上中文/英文/其他语言”, “添加翻译”, “做成双语版”, “变为双语版”,
  “保留原文”, “对照” or an affirmative request for a bilingual version means
  `bilingual`: retain the original language and add the requested target language.
  This explicit additive/bilingual intent takes precedence even when the same
  request also says “翻译为英文/中文”. Interpret negation normally: “不要双语版”
  is not an affirmative bilingual request.

Use `auto` only when neither intent is specified: ordinary documents replace text,
engineering drawings add bilingual text. Scan supports either mode; native-CAD
is specialized replacement for native/mixed engineering drawings. Determine
content with the router, not with the output-language wording.

In bilingual mode, preserve the exact source as already complete only when its
reviewed language pair matches the user's requested pair and every clear label
is semantically paired. A complete Chinese-English drawing does not satisfy a
Chinese-Spanish request. Use the PDF router's language-inventory contract;
missing pair evidence means continue inventory/translation, not failed delivery.
This shortcut never satisfies an explicit monolingual request.

For measured tests or resumed jobs, optional `formats/pdf/scripts/session_metrics.py`
records active wall time independently of adapter QA. From the repository root:

```powershell
python formats/pdf/scripts/session_metrics.py start --job <job> --source <source> --target-language zh --mode replace --pages 10 --budget-per-page 180
python formats/pdf/scripts/session_metrics.py checkpoint --job <job> --stage translate --status completed
python formats/pdf/scripts/session_metrics.py status --job <job>
```

Start at task entry; it cannot recover time spent before `start`. Tool gaps and
failed retries count; use `pause`/`resume --job <job>` only for an actual pause
or final completion. A helper such as image `finish` already freezes its execution
ledger: do not pause it again. Retain task-entry and final-handoff UTC separately
to include time outside that ledger. `completed` labels a checkpoint,
not the timer or QA. The timer's default is the 120-second optimization target;
for scan/image acceptance-ceiling tracking explicitly use `--budget-per-page 180`.
Other adapter budgets may use their own value. Same-request start preserves history; mismatched
source/request cannot overwrite it. Use one writer per job. This diagnostic tool
is optional, never a new delivery gate or a substitute for actual review.

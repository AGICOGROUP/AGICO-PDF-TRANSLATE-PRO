# Native-CAD Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a source-text replacement adapter for native/mixed engineering drawings while keeping bilingual output as the default engineering-drawing behavior.

**Architecture:** Keep `native-text`, `mixed`, and `scan-only` as the PDF content classifications. Select `native-cad` only from the combination `(native-text | mixed) + engineering-drawing + explicit replace`; `auto` retains the current bilingual drawing route. The adapter owns coordinate-bound replacement and its quality gates without merging with native, scan, or bilingual workflows.

**Tech Stack:** Python 3.12, pypdf, PyMuPDF, reportlab, unittest/pytest, Markdown Codex skills.

**Spec:** `docs/superpowers/specs/2026-09-04-native-cad-routing-design.md`

## Global Constraints

- Work only inside `E:\pdf-translate-pro`.
- Preserve existing `document_kind` values and scan/image behavior.
- Do not touch the user's unrelated scan-layout changes.
- Do not route scan-only PDFs to `native-cad`.
- Do not commit or stage unrelated dirty-worktree files.

---

### Task 1: Mode-aware PDF routing

**Files:**
- Modify: `formats/pdf/tests/test_route_pdf_file.py`
- Modify: `formats/pdf/scripts/route_pdf_file.py`

**Interfaces:**
- Consumes: CLI positional `source` and optional `--mode auto|replace|bilingual`.
- Produces: the existing JSON report shape with adapter and translation mode selected from PDF content, document kind, and requested mode.

- [ ] **Step 1: Write failing route tests**

Add test coverage that passes a mode to `run_router` and proves:

```python
def test_explicit_replace_routes_native_drawing_to_native_cad(self):
    source = self.make_large_drawing_pdf(path, "SECTION A-A")
    report = self.run_router(source, mode="replace")
    self.assertEqual("native-text", report["pdf_type"])
    self.assertEqual("engineering-drawing", report["document_kind"])
    self.assertEqual("formats/pdf/native-cad/SKILL.md", report["adapter"])
    self.assertEqual("replace", report["translation_mode"])

def test_auto_keeps_native_drawing_bilingual(self): ...
def test_explicit_bilingual_routes_general_native_pdf_to_bilingual(self): ...
def test_scan_never_routes_to_native_cad(self): ...
```

- [ ] **Step 2: Run the focused tests and observe the expected RED failure**

Run:

```powershell
python -m pytest formats/pdf/tests/test_route_pdf_file.py -q
```

Expected: new tests fail because `--mode` and `NATIVE_CAD_ADAPTER` do not exist.

- [ ] **Step 3: Implement minimal mode-aware routing**

Add `NATIVE_CAD_ADAPTER`, parse `--mode` with argparse choices, and pass mode into `route`. Preserve all existing validation. Use this decision order:

```python
if pdf_type == "scan-only":
    adapter = SCAN_ADAPTER
elif mode == "bilingual":
    adapter = BILINGUAL_ADAPTER
elif drawing and mode == "replace":
    adapter = NATIVE_CAD_ADAPTER
elif drawing:  # auto
    adapter = BILINGUAL_ADAPTER
else:
    adapter = NATIVE_ADAPTER
```

Set `translation_mode` consistently without changing `document_kind` detection.

- [ ] **Step 4: Run the focused tests and confirm GREEN**

Run the same pytest command and require zero failures.

### Task 2: Native-CAD adapter contract and pipeline

**Files:**
- Create: `formats/pdf/native-cad/SKILL.md`
- Create: `formats/pdf/native-cad/agents/openai.yaml`
- Create: `formats/pdf/native-cad/references/quality-gates.md`
- Create: `formats/pdf/native-cad/scripts/native_cad_pipeline.py`
- Create: `formats/pdf/native-cad/tests/test_native_cad_pipeline.py`

**Interfaces:**
- Consumes: `prepare SOURCE --job-dir DIR`, `apply JOB --packet JSON`, and `verify JOB --candidate PDF [--visual-review JSON]`.
- Produces: source-bound inventory, translation packet, translated PDF, apply report, and final QA JSON.

- [ ] **Step 1: Write failing pipeline contract tests**

Create a small reportlab drawing fixture with selectable horizontal and rotated labels plus vector lines. Test observable behavior:

```python
def test_prepare_binds_source_and_exports_stable_records(): ...
def test_apply_rejects_missing_translations(): ...
def test_apply_replaces_text_without_removing_vectors(): ...
def test_verify_requires_hash_bound_complete_visual_review(): ...
```

Assertions must cover stable IDs, protected engineering tokens, source SHA-256, page geometry, extractable translated text, vector drawing preservation, fit failures, and fail-closed final QA.

- [ ] **Step 2: Run the new tests and observe RED**

Run:

```powershell
python -m pytest formats/pdf/native-cad/tests/test_native_cad_pipeline.py -q
```

Expected: collection or command failures because the pipeline is absent.

- [ ] **Step 3: Implement the smallest complete source-bound pipeline**

Implement one script with three subcommands. `prepare` copies the immutable source, records its hash and page structure, and exports stable span records. `apply` validates every pending record, redacts text with `images=0, graphics=0, text=0`, inserts an embedded CJK font with preserved cardinal direction, records fit failures, and refuses unsafe Form/XObject covers. `verify` compares hashes and page structure, checks extractable target text and reports, requires a candidate-bound visual review, and writes `final-qa.json` with `passed` true only when every gate succeeds.

- [ ] **Step 4: Run the Native-CAD tests and confirm GREEN**

Run the focused test file until it passes with no warnings or skipped contract checks.

- [ ] **Step 5: Write and validate the adapter Skill**

Write a concise entrypoint that triggers only for native/mixed engineering drawings with explicit replacement intent, links the detailed quality gates, and forbids scan-only and bilingual use. Validate:

```powershell
$env:PYTHONUTF8='1'
python "$env:USERPROFILE\.codex\skills\.system\skill-creator\scripts\quick_validate.py" "formats/pdf/native-cad"
```

### Task 3: Synchronize router skills without changing other classifications

**Files:**
- Modify: `SKILL.md`
- Modify: `formats/pdf/SKILL.md`
- Modify: `formats/pdf/native/SKILL.md`
- Modify: `formats/pdf/bilingual/SKILL.md`

**Interfaces:**
- Consumes: router JSON fields `pdf_type`, `document_kind`, `translation_mode`, and `adapter`.
- Produces: one unambiguous instruction path to exactly one adapter.

- [ ] **Step 1: Record the baseline decision failure**

Using the current files, verify that an explicit replacement request for a native engineering drawing is still instructed to use bilingual output. Keep this as the documented RED behavior; do not create brittle text-matching tests.

- [ ] **Step 2: Apply the minimal instruction changes**

State these two rules consistently at every routing boundary:

```text
Engineering drawing + auto/ordinary wording -> bilingual by default.
Native/mixed engineering drawing + explicit replace -> native-cad.
```

Describe `native-cad` as a specialized execution adapter selected from combined conditions, never as a fourth PDF content classification. Leave Office scope, `document_kind`, scan, and image rules unchanged.

- [ ] **Step 3: Validate every changed Skill**

Run `quick_validate.py` for the root, PDF router, native, bilingual, and native-cad skill folders. Inspect the rendered decision table for contradictions and dangling paths.

### Task 4: Regression verification

**Files:**
- Test only; do not modify unrelated failing areas.

**Interfaces:**
- Consumes: all changed scripts and skills.
- Produces: fresh verification evidence.

- [ ] **Step 1: Compile changed Python files**

```powershell
python -m py_compile formats/pdf/scripts/route_pdf_file.py formats/pdf/native-cad/scripts/native_cad_pipeline.py
```

- [ ] **Step 2: Run focused suites**

```powershell
python -m pytest formats/pdf/tests formats/pdf/native-cad/tests -q
```

- [ ] **Step 3: Run the repository PDF/image regression command**

```powershell
python -m pytest formats/pdf/native/tests formats/pdf/scan/tests formats/pdf/bilingual/tests formats/image/tests formats/pdf/tests -q
```

Also run `python -m pytest test_independent_quality_gates.py -q` when that root test exists.

- [ ] **Step 4: Review the final diff and scope**

Confirm no unrelated dirty-worktree files changed, no scan/image classification changed, no adapter path is missing, and the two approved routing rules are consistent in code and skills.

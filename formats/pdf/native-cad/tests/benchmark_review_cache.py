"""Synthetic render-only comparison against the archived stable implementation.

Run from the repository root. No prior translations or OCR results are loaded.
"""
import hashlib
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time
import types
import zipfile

import pymupdf

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT/'formats/pdf/native-cad/scripts'))
import cad_batch
from cad_units import propose_units


def make_pdf(path, changed=False):
    with pymupdf.open() as doc:
        for number in range(8):
            page = doc.new_page(width=700, height=900)
            for row in range(30):
                page.insert_text((30, 35+row*27),
                    f'Item {row}: '+('Changed' if changed and number == 7 else 'Original'))
                page.draw_line((25,45+row*27),(675,45+row*27))
        doc.save(path)


def main():
    runs = ROOT/'tmp/cad-review-benchmark-20260911'
    runs.mkdir(parents=True, exist_ok=True)
    # Never label a previous run's cached artifacts as a cold build.
    destination = Path(tempfile.mkdtemp(prefix='run-', dir=runs))
    archive = ROOT/'tmp/refactor-baselines/dade7e53/source.zip'
    assert hashlib.sha256(archive.read_bytes()).hexdigest().upper() == 'C72B200419EE28B6212122A3989BEEDA7E09E051DEBDBC690C2F76084CAA0055'
    with zipfile.ZipFile(archive) as saved:
        code = saved.read('formats/pdf/native-cad/scripts/cad_batch.py')
    old = types.ModuleType('baseline_cad_batch')
    exec(compile(code, str(archive)+'!cad_batch.py', 'exec'), old.__dict__)
    source, target = destination/'source.pdf', destination/'candidate.pdf'
    make_pdf(source)
    records = [dict(id=f'p{p}-r{r}', page=p, bbox=[25,20+r*27,200,38+r*27],
                    source=f'Item {r}', translation='Synthetic') for p in range(8) for r in range(30)]
    results = []
    for repeat in range(3):
        row = {}
        for name, module in [('baseline',old),('current',cad_batch)]:
            output = destination/str(repeat)/name
            make_pdf(target)
            started = time.perf_counter()
            module.review_bundle(source, output, records, target)
            row[name+'_cold_seconds'] = time.perf_counter()-started
            make_pdf(target, changed=True)
            started = time.perf_counter()
            report = module.review_bundle(source, output, records, target)
            row[name+'_repair_seconds'] = time.perf_counter()-started
            if name == 'current':
                assert report['reused_pages'] == list(range(7))
                assert report['rebuilt_pages'] == [7]
        baseline, current = destination/str(repeat)/'baseline', destination/str(repeat)/'current'
        for path in baseline.glob('*.png'):
            a, b = pymupdf.Pixmap(str(path)), pymupdf.Pixmap(str(current/path.name))
            assert (a.width,a.height,a.samples) == (b.width,b.height,b.samples), path.name
        row['all_review_pixels_equal'] = True
        results.append(row)
    summary = {k:statistics.median(r[k] for r in results) for k in results[0] if k.endswith('seconds')}
    summary['repair_reduction_percent'] = 100*(1-summary['current_repair_seconds']/summary['baseline_repair_seconds'])
    result = dict(scope='8 synthetic pages, 240 review crops; render only, no OCR or translation timing',
                  repetitions=results, medians=summary)
    # This is source extraction only, not translated text or a fresh-job timing.
    inventory_path = ROOT/'tmp/pdfs/despiece-fijacion-zh-db88d938/source-inventory.json'
    if inventory_path.exists():
        inventory = json.loads(inventory_path.read_text(encoding='utf-8'))
        proposals = propose_units(inventory)
        pending = sum(r['status']=='pending' for r in inventory['records'])
        result['source_grouping'] = dict(source_sha256=inventory['source_sha256'],
            pending_records=pending, proposed_units=len(proposals['units']),
            grouped_units=sum(len(u['member_ids'])>1 for u in proposals['units']),
            note='Existing source-only extraction; no prior translations used. Cell proposals may be absent in legacy inventory.')
    (destination/'results.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(str(destination/'results.json'))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()

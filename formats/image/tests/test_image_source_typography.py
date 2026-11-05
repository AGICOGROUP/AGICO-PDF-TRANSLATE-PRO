"""Fresh source geometry must govern image role typography, independent of OCR DPI."""
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'formats/image/scripts'))
from image_job import import_rows


def write_job(tmp_path, scale=1, rotation=0, styles=None):
    job = tmp_path / 'job'
    (job / 'extract').mkdir(parents=True)
    (job / 'manifest').mkdir()
    lines = []
    for index, (role, height) in enumerate([('heading', 48), ('body', 44), ('body', 46), ('body', 90), ('footer', 24)], 1):
        box = [100, index * 120, 700, index * 120 + height]
        if rotation in (90, 270):
            box = [index * 120, 100, index * 120 + height, 700]
        lines.append({'id': f'p01-l{index:03}', 'page': 1, 'text': role,
                      'box': [value * scale for value in box], 'rotation': rotation})
    extraction = {'source_sha256': 'a' * 64, 'pages': [{'pixel_width': 1400 * scale,
                  'pixel_height': 900 * scale, 'width_pt': 1400, 'height_pt': 900}], 'source_lines': lines}
    (job / 'extract/extraction-report.json').write_text(json.dumps(extraction), encoding='utf-8')
    (job / 'image-metadata.json').write_text(json.dumps({'pixel_size': [1400, 900]}), encoding='utf-8')
    (job / 'manifest/decisions.json').write_text(json.dumps({'target_language': 'en', 'styles': styles or {}}), encoding='utf-8')
    rows = tmp_path / 'rows.tsv'
    rows.write_text('1\theading\tMachine\n2-4\tbody\tTechnical specifications\n5\tfooter\tManufacturer\n', encoding='utf-8')
    return job, rows


@pytest.mark.parametrize('scale,rotation', [(1, 0), (4, 0), (2, 90), (3, 270), (2, 180)])
def test_default_role_baselines_follow_source_glyph_height_not_carrier_or_ocr_dpi(tmp_path, scale, rotation):
    job, rows = write_job(tmp_path, scale, rotation)
    import_rows(job, rows)
    styles = json.loads((job / 'manifest/decisions.json').read_text(encoding='utf-8'))['styles']
    # Median body glyphs (44, 46, 90), not the union height or the outlier.
    assert styles['body']['max_font'] == pytest.approx(46 / 1.12)
    assert styles['heading']['max_font'] > styles['body']['max_font'] > styles['footer']['max_font']
    assert styles['body']['min_font'] >= styles['body']['max_font'] * 0.6


def test_import_keeps_agent_authored_typography_overrides(tmp_path):
    overrides = {'body': {'max_font': 35, 'min_font': 30, 'color': [1, 0, 0]},
                 'heading': {'bold': False}, 'custom': {'align': 'right'}}
    job, rows = write_job(tmp_path, styles=overrides)
    import_rows(job, rows)
    styles = json.loads((job / 'manifest/decisions.json').read_text(encoding='utf-8'))['styles']
    for role, fields in overrides.items():
        assert all(styles[role][key] == value for key, value in fields.items())
    assert styles['heading']['max_font'] > 35


def test_supplement_defaults_use_original_image_pixel_geometry(tmp_path):
    job, rows = write_job(tmp_path, scale=4)
    rows.write_text('+label\tbody\tPower\t100,100,600,145\t功率\n', encoding='utf-8')
    import_rows(job, rows)
    decisions = json.loads((job / 'manifest/decisions.json').read_text(encoding='utf-8'))
    assert decisions['styles']['body']['max_font'] == pytest.approx(45 / 1.12)


def test_reimport_refreshes_source_defaults_but_preserves_manual_edits(tmp_path):
    job, rows = write_job(tmp_path)
    import_rows(job, rows)
    path = job / 'manifest/decisions.json'
    decisions = json.loads(path.read_text(encoding='utf-8'))
    decisions['styles']['heading']['max_font'] = 60
    path.write_text(json.dumps(decisions), encoding='utf-8')
    rows.write_text('1\theading\tMachine\n2\tbody\tPower\n3-4\tpreserve\tNeutral identifiers\n5\tfooter\tMaker\n', encoding='utf-8')
    import_rows(job, rows)
    decisions = json.loads(path.read_text(encoding='utf-8'))
    assert decisions['styles']['heading']['max_font'] == 60
    assert decisions['styles']['body']['max_font'] == pytest.approx(44 / 1.12)


def test_maximum_only_override_does_not_create_an_invalid_minimum(tmp_path):
    job, rows = write_job(tmp_path, styles={'body': {'max_font': 20}})
    import_rows(job, rows)
    styles = json.loads((job / 'manifest/decisions.json').read_text(encoding='utf-8'))['styles']
    assert styles['body']['max_font'] == 20
    assert styles['body']['min_font'] <= 20


def test_row_reimport_keeps_established_source_language(tmp_path):
    job, rows = write_job(tmp_path)
    path = job/'manifest/decisions.json'
    decisions = json.loads(path.read_text(encoding='utf-8'))
    decisions['source_language'] = 'en-US'
    path.write_text(json.dumps(decisions), encoding='utf-8')
    import_rows(job, rows)
    import_rows(job, rows)
    assert json.loads(path.read_text(encoding='utf-8'))['source_language'] == 'en-US'

import copy
import sys
from pathlib import Path

import pymupdf
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import native_cad_pipeline as cad
from cad_units import propose_units


@pytest.mark.parametrize('barrier', ['rotation', 'multiline', 'color', 'outline'])
def test_conservative_units_do_not_join_different_structures(barrier):
    records = [dict(id='a', page=0, bbox=[10,10,30,20], source='VISTA', status='pending'),
               dict(id='b', page=0, bbox=[35,10,70,20], source='INFERIOR', status='pending')]
    if barrier == 'rotation':
        records[1]['rotation'] = 90
    elif barrier == 'multiline':
        records[1]['bbox'] = [10,25,45,35]
    elif barrier == 'color':
        records[1]['color'] = 255
    else:
        records[1]['kind'] = 'outline'
    assert len(propose_units(dict(records=records, source_sha256='s'))['units']) == 2


def prepare_words(tmp_path, *, border=False, protected=False):
    source = tmp_path / 'source.pdf'
    with pymupdf.open() as doc:
        page = doc.new_page(width=400, height=200)
        page.insert_text((30, 50), 'VISTA')
        if protected:
            page.insert_text((70, 50), '20')
        page.insert_text((90, 50), 'INFERIOR')
        if border:
            page.draw_rect([20, 20, 80, 70])
            page.draw_rect([80, 20, 180, 70])
        doc.save(source)
    job = tmp_path / 'job'
    assert cad.prepare(source, job, ocr='never', target_language='zh') == 0
    return source, job


def test_prepare_exports_coherent_units_and_import_draws_once(tmp_path):
    source, job = prepare_words(tmp_path)
    units_path = job / 'translation-units.json'
    assert units_path.exists(), 'prepare should export context-bound translation units'
    units = cad.read_json(units_path)
    assert len(units['units']) == 1
    unit = units['units'][0]
    assert unit['source'] == 'VISTA INFERIOR'
    assert len(unit['member_ids']) == 2
    assert 'VISTA' in units['pages'][0]['text']
    unit.update(translation='底视图', review_note='One view label, read as a phrase.')
    translated = job / 'unit-translations.json'
    cad.write_json(translated, units)
    assert cad.merge_units(job, translated) == 0
    packet = cad.read_json(job / cad.PACKET_NAME)
    assert [r['status'] for r in packet['records']] == ['translated', 'merged']
    assert cad.apply(job, job / cad.PACKET_NAME, cad.DEFAULT_FONT) == 0
    with pymupdf.open(job / cad.OUTPUT_NAME) as doc:
        assert doc[0].get_text().count('底视图') == 1
        assert 'VISTA' not in doc[0].get_text()


@pytest.mark.parametrize('barrier', ['cell', 'dimension'])
def test_units_do_not_cross_table_cells_or_protected_dimensions(tmp_path, barrier):
    _, job = prepare_words(tmp_path, border=barrier == 'cell', protected=barrier == 'dimension')
    path = job / 'translation-units.json'
    assert path.exists()
    units = cad.read_json(path)
    assert len(units['units']) == 2
    assert all(len(u['member_ids']) == 1 for u in units['units'])
    if barrier == 'dimension':
        assert '20' in units['pages'][0]['text']


@pytest.mark.parametrize('change', ['source', 'members', 'binding', 'duplicate', 'cell_escape'])
def test_unit_import_rejects_conflicts_without_partial_packet_writes(tmp_path, change):
    _, job = prepare_words(tmp_path, border=change == 'cell_escape')
    path = job / 'translation-units.json'
    assert path.exists()
    units = cad.read_json(path)
    for unit in units['units']:
        unit.update(translation='底视图', review_note='Reviewed unit.')
    if change == 'source':
        units['units'][0]['source'] = 'wrong original'
    elif change == 'members':
        units['units'][0]['member_ids'] = ['unknown-id']
    elif change == 'binding':
        units['inventory_sha256'] = 'stale'
    elif change == 'duplicate':
        units['units'].append(copy.deepcopy(units['units'][0]))
    else:
        units['units'][0]['layout_box'] = [20, 20, 180, 70]
    translated = job / 'unit-translations.json'
    cad.write_json(translated, units)
    before = (job / cad.PACKET_NAME).read_bytes()
    assert cad.merge_units(job, translated) != 0
    assert (job / cad.PACKET_NAME).read_bytes() == before


def test_units_remain_stable_on_resume_and_keep_translations(tmp_path):
    source, job = prepare_words(tmp_path)
    path = job / 'translation-units.json'
    assert path.exists()
    first = cad.read_json(path)
    first['units'][0].update(translation='底视图', review_note='One phrase.')
    approved = job / 'unit-translations.json'
    cad.write_json(approved, first)
    assert cad.merge_units(job, approved) == 0
    before = (job / cad.PACKET_NAME).read_bytes()
    assert cad.prepare(source, job, ocr='never', target_language='zh') == 0
    assert cad.read_json(path)['inventory_sha256'] == first['inventory_sha256']
    assert cad.read_json(job / cad.PACKET_NAME)['records'][0]['translation'] == '底视图'

import sys
from pathlib import Path

import pymupdf
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import native_cad_pipeline as cad


def test_motor_and_instrument_tokens_are_not_translations():
    assert cad.is_protected('M')
    assert cad.is_protected('PIT')
    assert not cad.is_protected('LIME SILO')


def test_prepare_resume_keeps_translations(tmp_path):
    source = tmp_path / 'input.pdf'
    with pymupdf.open() as doc:
        doc.new_page().insert_text((50, 50), 'LIME SILO')
        doc.save(source)
    job = tmp_path / 'job'
    cad.prepare(source, job)
    packet = cad.read_json(job / cad.PACKET_NAME)
    packet['records'][0].update(translation='石灰仓', status='translated')
    cad.write_json(job / cad.PACKET_NAME, packet)
    cad.prepare(source, job)
    assert cad.read_json(job / cad.PACKET_NAME)['records'][0]['translation'] == '石灰仓'


def test_cover_blocks_crossing_pipe_and_contained_symbol():
    from cad_outline import cover_conflicts
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.draw_line((10, 50), (200, 50))
        page.draw_circle((100, 100), 5)
        assert cover_conflicts(page, [40, 40, 80, 60])
        assert cover_conflicts(page, [90, 90, 110, 110])
        assert not cover_conflicts(page, [40, 140, 80, 160])


def test_enclosing_frame_does_not_block_empty_interior():
    from cad_outline import cover_conflicts
    with pymupdf.open() as doc:
        p = doc.new_page()
        p.draw_rect([5, 5, 500, 700])
        assert not cover_conflicts(p, [40, 140, 80, 160])


def test_small_contained_quad_can_be_reviewed_as_outline_glyph():
    from cad_outline import cover_conflicts
    with pymupdf.open() as doc:
        p = doc.new_page()
        p.draw_rect([42, 142, 48, 148])
        assert not cover_conflicts(p, [40, 140, 80, 160])


def test_duplicate_packet_ids_rejected():
    record = dict(id='a', source='Silo', status='pending')
    translated = dict(id='a', source='Silo', status='translated', translation='仓')
    _, failures = cad.validate_packet({'records': [record]}, {'records': [translated, translated]})
    assert failures


def test_dismissal_requires_source_review_reason():
    inv = {'records': [dict(id='a', source='noise', status='pending', kind='outline')]}
    entry = dict(id='a', source='noise', status='dismissed')
    assert cad.validate_packet(inv, {'records': [entry]})[1]
    entry['review_note'] = 'Source crop shows an arrow, not text.'
    assert not cad.validate_packet(inv, {'records': [entry]})[1]


def test_review_template_is_incomplete_and_matches_contract(tmp_path):
    cad.write_review_template(tmp_path, 'abc')
    review = cad.read_json(tmp_path / 'visual-review.template.json')
    assert review['candidate_sha256'] == 'abc'
    assert review['all_pages_reviewed'] is False
    assert 'visible_foreign_descriptive_text' in review


def test_ocr_is_cached_and_native_duplicates_removed(tmp_path):
    from cad_outline import extract_outline_records
    source = tmp_path / 'input.pdf'
    with pymupdf.open() as doc:
        page = doc.new_page(width=300, height=200)
        page.insert_text((20, 40), 'LIME SILO')
        page.draw_line((100, 80), (110, 90))
        doc.save(source)
    calls = []
    def engine(image):
        calls.append(True)
        return [([[200, 150], [260, 150], [260, 175], [200, 175]], '石灰仓', .98)], None
    with pymupdf.open(source) as doc:
        native = cad.extract_records(doc)
        a, _ = extract_outline_records(doc, tmp_path, cad.sha256(source), native, engine=engine)
        b, _ = extract_outline_records(doc, tmp_path, cad.sha256(source), native, engine=engine)
    assert len(calls) == 1
    assert a == b and a[0]['source'] == '石灰仓'
    # An interrupted write must not poison all subsequent resume attempts.
    next((tmp_path / 'ocr-cache').glob('*.json')).write_text('{', encoding='utf-8')
    with pymupdf.open(source) as doc:
        recovered, _ = extract_outline_records(doc, tmp_path, cad.sha256(source), native, engine=engine)
    assert recovered == a


def test_typography_baseline_does_not_follow_each_ocr_box():
    records = [dict(id=str(i), page=0, font_size=size) for i, size in enumerate([10, 11, 20])]
    packet = {r['id']: {'role': 'body'} for r in records}
    baselines = cad.typography_baselines(records, packet)
    assert baselines[(0, 'body')] == 11


def test_reviewed_cover_replaces_only_region_and_retains_vectors(tmp_path):
    source = tmp_path / 'input.pdf'
    with pymupdf.open() as doc:
        p = doc.new_page(width=200, height=200)
        p.draw_line((25, 30), (30, 35))  # outline glyph stroke, confirmed by pixel review
        p.draw_line((0, 100), (200, 100))  # engineering line to retain exactly
        doc.save(source)
    job = tmp_path / 'job'
    cad.prepare(source, job)
    inventory = cad.read_json(job / cad.INVENTORY_NAME)
    record = dict(id='p0001-o00001', source='仓', page=0, bbox=[20, 20, 75, 45],
                  kind='outline', status='pending', font_size=10, color=0, rotation=0)
    inventory['records'].append(record)
    cad.write_json(job / cad.INVENTORY_NAME, inventory)
    packet = cad.read_json(job / cad.PACKET_NAME)
    packet['records'].append(dict(id=record['id'], source='仓', translation='Silo', status='translated',
                                 cover_review=dict(approved=True, text_only=True, white_background=True, note='Inspected isolated glyph stroke on white background.')))
    cad.write_json(job / cad.PACKET_NAME, packet)
    assert cad.apply(job, job / cad.PACKET_NAME, cad.DEFAULT_FONT) == 0
    with pymupdf.open(source) as original, pymupdf.open(job / cad.OUTPUT_NAME) as result:
        assert 'Silo' in result[0].get_text()
        assert len(result[0].get_drawings()) >= len(original[0].get_drawings())
        clip = pymupdf.Rect(0, 90, 200, 110)
        assert original[0].get_pixmap(clip=clip).samples == result[0].get_pixmap(clip=clip).samples


def test_reviewed_cover_can_restore_a_crossing_pipe(tmp_path):
    source = tmp_path / 'input.pdf'
    with pymupdf.open() as doc:
        p = doc.new_page(width=200, height=200)
        p.draw_line((25, 30), (30, 35))
        p.draw_line((0, 32), (200, 32))
        doc.save(source)
    job = tmp_path / 'job'
    cad.prepare(source, job)
    inventory = cad.read_json(job / cad.INVENTORY_NAME)
    record = dict(id='p0001-o00001', source='仓', page=0, bbox=[20, 20, 75, 45],
                  kind='outline', status='pending', font_size=10, color=0, rotation=0)
    inventory['records'].append(record)
    cad.write_json(job / cad.INVENTORY_NAME, inventory)
    packet = cad.read_json(job / cad.PACKET_NAME)
    packet['records'].append(dict(id=record['id'], source='仓', translation='Silo', status='translated',
        cover_review=dict(approved=True, text_only=True, white_background=True,
                          restore_conflicting_paths=True,
                          note='Inspected isolated glyph crossed by one straight pipe; restore it exactly.')))
    cad.write_json(job / cad.PACKET_NAME, packet)
    assert cad.apply(job, job / cad.PACKET_NAME, cad.DEFAULT_FONT) == 0
    with pymupdf.open(job / cad.OUTPUT_NAME) as result:
        pix = result[0].get_pixmap(matrix=pymupdf.Matrix(4, 4), clip=[35, 31, 65, 33], alpha=False)
        assert min(pix.samples) < 40


def test_cover_only_removes_bilingual_source_when_target_is_already_present(tmp_path):
    source = tmp_path / 'input.pdf'
    with pymupdf.open() as doc:
        p = doc.new_page(width=200, height=100)
        p.draw_line((20, 20), (30, 30))
        p.insert_text((80, 30), 'SILO')
        doc.save(source)
    job = tmp_path / 'job'
    cad.prepare(source, job)
    inventory = cad.read_json(job / cad.INVENTORY_NAME)
    record = dict(id='p0001-o00001', source='仓', page=0, bbox=[15, 15, 35, 35],
                  kind='outline', status='pending', font_size=10, color=0, rotation=0)
    inventory['records'].append(record)
    cad.write_json(job / cad.INVENTORY_NAME, inventory)
    packet = cad.read_json(job / cad.PACKET_NAME)
    for native in packet['records']:
        native.update(status='preserved', review_note='Existing target-language label remains unchanged.')
    packet['records'].append(dict(id=record['id'], source='仓', status='cover_only',
        target_present='SILO', review_note='The English target is printed beside the Chinese label.',
        cover_review=dict(approved=True, text_only=True, white_background=True,
                          note='Fresh source crop reviewed.')))
    cad.write_json(job / cad.PACKET_NAME, packet)
    assert cad.apply(job, job / cad.PACKET_NAME, cad.DEFAULT_FONT) == 0
    with pymupdf.open(job / cad.OUTPUT_NAME) as result:
        assert result[0].get_text().count('SILO') == 1

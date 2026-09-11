import sys
from pathlib import Path

import pymupdf
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import native_cad_pipeline as cad


@pytest.mark.parametrize('overflow', [False, True])
def test_phrase_drawn_once_or_all_source_retained(tmp_path, overflow):
    source = tmp_path / 'source.pdf'
    with pymupdf.open() as doc:
        page = doc.new_page(width=400, height=200)
        page.insert_text((30, 50), 'VISTA')
        page.insert_text((150, 50), 'INFERIOR')
        page.draw_line((20, 100), (350, 100))
        doc.save(source)
    job = tmp_path / 'job'
    cad.prepare(source, job, ocr='never')
    packet = cad.read_json(job / cad.PACKET_NAME)
    leader, member = packet['records']
    leader.update(status='translated', translation='底视图' if not overflow else '长句' * 10000,
                  layout_box=[30, 35, 230, 60])
    member.update(status='merged', merged_into=leader['id'],
                  review_note='Both words form one view label.')
    cad.write_json(job / cad.PACKET_NAME, packet)
    result = cad.apply(job, job / cad.PACKET_NAME, cad.DEFAULT_FONT)
    report = cad.read_json(job / cad.APPLY_REPORT_NAME)
    path = Path(report['preview']) if overflow else job / cad.OUTPUT_NAME
    with pymupdf.open(path) as doc:
        text = doc[0].get_text()
        assert len(doc[0].get_drawings()) == 1
        if overflow:
            assert result != 0
            assert 'VISTA' in text and 'INFERIOR' in text
            assert set(report['source_retained_ids']) == {leader['id'], member['id']}
        else:
            assert result == 0
            assert text.count('底视图') == 1
            assert 'VISTA' not in text and 'INFERIOR' not in text


def test_merge_rejects_missing_leader_and_cross_page():
    records = [dict(id='a', source='VISTA', page=0, rotation=0, status='pending'),
               dict(id='b', source='INFERIOR', page=1, rotation=0, status='pending')]
    packet = {'records': [dict(records[0], status='translated', translation='底视图', layout_box=[0,0,100,30]),
                          dict(records[1], status='merged', merged_into='a', review_note='phrase')]}
    assert 'b' in cad.validate_packet({'records': records}, packet)[1]
    packet['records'][1]['merged_into'] = 'missing'
    assert 'b' in cad.validate_packet({'records': records}, packet)[1]


def test_normal_font_and_outline_height_do_not_inflate_baseline():
    for kind in ('native', 'outline'):
        record = dict(id='a', page=0, font_size=10, bbox=[0,0,100,18], kind=kind)
        assert cad.typography_baselines([record], {'a': {'role': 'body'}})[(0,'body')] == 10

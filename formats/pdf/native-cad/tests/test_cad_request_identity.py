import json
import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import native_cad_pipeline as cad


def source_pdf(tmp_path):
    source = tmp_path / 'source.pdf'
    with pymupdf.open() as doc:
        doc.new_page(width=400, height=200).insert_text((30, 50), 'VIEW')
        doc.save(source)
    return source


def test_cad_target_change_requires_new_job_without_overwriting(tmp_path):
    source = source_pdf(tmp_path)
    job = tmp_path / 'job'
    assert cad.prepare(source, job, ocr='never', target_language='zh-CN') == 0
    packet = (job / cad.PACKET_NAME).read_bytes()
    inventory = (job / cad.INVENTORY_NAME).read_bytes()
    assert cad.prepare(source, job, ocr='never', target_language='es') != 0
    assert (job / cad.PACKET_NAME).read_bytes() == packet
    assert (job / cad.INVENTORY_NAME).read_bytes() == inventory
    assert cad.prepare(source, job, ocr='never', target_language='ZH_cn') == 0


def test_cad_fresh_creates_independent_job_and_packet_intent_is_checked(tmp_path, capsys):
    source = source_pdf(tmp_path)
    job = tmp_path / 'job'
    assert cad.prepare(source, job, ocr='never', target_language='zh') == 0
    packet = cad.read_json(job / cad.PACKET_NAME)
    packet['records'][0].update(status='translated', translation='视图')
    cad.write_json(job / cad.PACKET_NAME, packet)
    before = (job / cad.PACKET_NAME).read_bytes()
    assert cad.prepare(source, job, ocr='never', target_language='es', fresh=True) == 0
    fresh = Path(json.loads(capsys.readouterr().out.splitlines()[-1])['job_dir'])
    assert fresh != job
    assert (job / cad.PACKET_NAME).read_bytes() == before
    assert cad.read_json(fresh / cad.PACKET_NAME)['records'][0]['translation'] == ''
    packet['request']['target_language'] = 'es'
    cad.write_json(job / cad.PACKET_NAME, packet)
    assert cad.apply(job, job / cad.PACKET_NAME, cad.DEFAULT_FONT) != 0
    assert 'packet_request_mismatch' in cad.read_json(job / cad.APPLY_REPORT_NAME)['failures']

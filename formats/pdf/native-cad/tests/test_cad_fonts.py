import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import native_cad_pipeline as cad


def translated_job(tmp_path, text):
    source = tmp_path / 'source.pdf'
    with pymupdf.open() as doc:
        doc.new_page(width=600, height=200).insert_text((20, 60), 'Drawing title')
        doc.save(source)
    job = tmp_path / 'job'
    assert cad.prepare(source, job) == 0
    packet = cad.read_json(job / cad.PACKET_NAME)
    packet['records'][0].update(status='translated', translation=text,
                                layout_box=[20, 30, 580, 100])
    cad.write_json(job / cad.PACKET_NAME, packet)
    return job


def test_french_missing_glyphs_fall_back_and_survive_pdf_extraction(tmp_path):
    text = 'Contrôlé Conçu Échelle œuvre'
    job = translated_job(tmp_path, text)
    assert cad.apply(job, job / cad.PACKET_NAME, cad.DEFAULT_FONT) == 0
    with pymupdf.open(job / cad.OUTPUT_NAME) as doc:
        assert text in doc[0].get_text()


def test_unsupported_character_fails_before_output(tmp_path):
    job = translated_job(tmp_path, 'Unsupported \U0010ffff')
    assert cad.apply(job, job / cad.PACKET_NAME, cad.DEFAULT_FONT) == 2
    report = cad.read_json(job / cad.APPLY_REPORT_NAME)
    assert 'font_missing_glyphs' in report['failures']
    assert 'U+10FFFF' in report['missing_glyphs']
    assert not (job / cad.OUTPUT_NAME).exists()


def test_supported_font_is_kept(tmp_path):
    job = translated_job(tmp_path, 'Drawing')
    assert cad.apply(job, job / cad.PACKET_NAME, cad.DEFAULT_FONT) == 0
    report = cad.read_json(job / cad.APPLY_REPORT_NAME)
    assert report['font_file'] == str(cad.DEFAULT_FONT)

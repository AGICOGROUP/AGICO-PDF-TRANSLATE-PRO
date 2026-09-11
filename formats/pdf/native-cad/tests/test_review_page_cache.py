import sys
from pathlib import Path

import pymupdf
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import cad_batch


def document(path, second='B', rotation=0):
    with pymupdf.open() as doc:
        for text in ['A', second]:
            page = doc.new_page(width=300, height=200)
            page.insert_text((30, 50), text)
            page.set_rotation(rotation)
        doc.save(path)


def test_repair_reuses_only_unchanged_pages_and_recovers_corrupt_artifacts(tmp_path):
    source, target, out = tmp_path/'s.pdf', tmp_path/'t.pdf', tmp_path/'review'
    document(source)
    document(target)
    records = [dict(id=f'p{i}', page=i, bbox=[25, 30, 60, 55], source='label') for i in range(2)]
    cad_batch.review_bundle(source, out, records, target)
    old = (out/'source-1.png').stat().st_mtime_ns
    document(target, 'CHANGED')
    report = cad_batch.review_bundle(source, out, records, target)
    assert report['reused_pages'] == [0]
    assert report['rebuilt_pages'] == [1]
    assert (out/'source-1.png').stat().st_mtime_ns == old
    (out/'region-0-source.png').write_bytes(b'bad')
    report = cad_batch.review_bundle(source, out, records, target)
    assert report['rebuilt_pages'] == [0]
    assert report['reused_pages'] == [1]
    records.pop()
    report = cad_batch.review_bundle(source, out, records, target)
    assert report['regions'] == ['p0']
    assert 'region-1-source.png' not in report['artifacts']


def test_rotated_review_crop_uses_display_coordinates(tmp_path):
    source, out = tmp_path/'s.pdf', tmp_path/'review'
    document(source, rotation=90)
    box = [25, 30, 60, 55]
    cad_batch.review_bundle(source, out, [dict(id='a', page=0, bbox=box)])
    with pymupdf.open(source) as doc:
        page = doc[0]
        rect = ((pymupdf.Rect(box)+(-8,-8,8,8))*page.rotation_matrix) & page.rect
        expected = page.get_pixmap(matrix=pymupdf.Matrix(2,2), clip=rect, alpha=False)
    actual = pymupdf.Pixmap(str(out/'region-0-source.png'))
    assert (actual.width, actual.height, actual.samples) == (expected.width, expected.height, expected.samples)


def test_residual_review_ocr_is_page_local_lazy_and_identity_bound(tmp_path, monkeypatch):
    import rapidocr_onnxruntime
    calls, constructed = [], []
    def factory():
        constructed.append(True)
        def engine(pixels):
            calls.append(True)
            return [], None
        return engine
    monkeypatch.setattr(rapidocr_onnxruntime, 'RapidOCR', factory)
    monkeypatch.setattr(cad_batch, 'ocr_identity', lambda: 'runtime-one')
    source, target, out = tmp_path/'s.pdf', tmp_path/'t.pdf', tmp_path/'review'
    document(source)
    document(target)
    cad_batch.review_bundle(source, out, [], target, residual_script='latin')
    assert (len(calls), len(constructed)) == (2, 1)
    monkeypatch.setattr(cad_batch, 'REVIEW_CACHE_VERSION', 999)
    cad_batch.review_bundle(source, out, [], target, residual_script='latin')
    assert (len(calls), len(constructed)) == (2, 1)
    document(target, 'changed')
    report = cad_batch.review_bundle(source, out, [], target, residual_script='latin')
    assert report['reused_pages'] == [0]
    assert (len(calls), len(constructed)) == (3, 2)
    monkeypatch.setattr(cad_batch, 'ocr_identity', lambda: 'runtime-two')
    cad_batch.review_bundle(source, out, [], target, residual_script='latin')
    assert (len(calls), len(constructed)) == (5, 3)


@pytest.mark.parametrize('rotation', [90,180,270])
def test_full_page_ocr_derotates_coordinates(tmp_path, rotation):
    with pymupdf.open() as doc:
        page = doc.new_page(width=200,height=100)
        page.set_rotation(rotation)
        original = pymupdf.Rect(20,30,60,50)
        pixel = (original * page.rotation_matrix) * 2
        def engine(_):
            return [([list(pixel.tl),list(pixel.tr),list(pixel.br),list(pixel.bl)],'label',.99)], None
        result, hit = cad_batch.page_ocr(page, 's', tmp_path/'ocr', engine)
        assert result[0]['bbox'] == pytest.approx(list(original))
        assert not hit


def test_page_cache_metadata_corruption_rebuilds_only_affected_page(tmp_path):
    import json
    source, out = tmp_path/'s.pdf', tmp_path/'review'
    document(source)
    cad_batch.review_bundle(source, out, [])
    path = out/'review-page-1.json'
    envelope = json.loads(path.read_text())
    envelope['payload']['body'] = ['wrong cached content']
    path.write_text(json.dumps(envelope))
    report = cad_batch.review_bundle(source, out, [])
    assert report['rebuilt_pages'] == [0]
    assert report['reused_pages'] == [1]
    assert 'wrong cached content' not in (out/'index.html').read_text()

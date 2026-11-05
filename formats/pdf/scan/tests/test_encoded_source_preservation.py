import hashlib
import io
import sys
from pathlib import Path

import numpy as np
import pymupdf
import pytest
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import build_scan


def jpeg_manifest(tmp_path, hidden=False):
    rng = np.random.default_rng(4321)
    pixels = np.clip(rng.normal(230, 12, (1000, 800, 3)), 0, 255).astype('uint8')
    pixels[30:50, 30:130] = 0
    stream = io.BytesIO()
    Image.fromarray(pixels).save(stream, format='JPEG', quality=65)
    source = tmp_path / 'source.pdf'
    c = canvas.Canvas(str(source), pagesize=(400, 500))
    c.drawImage(ImageReader(stream), 0, 0, width=400, height=500)
    if hidden:
        text = c.beginText(20, 400)
        text.setTextRenderMode(3)
        text.textLine('old hidden source')
        c.drawText(text)
    c.save()
    render = tmp_path / 'render.png'
    with pymupdf.open(source) as doc:
        doc[0].get_pixmap(matrix=pymupdf.Matrix(2, 2)).save(render)
    return {'source': str(source), 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
            'selected_pages': [1], 'target_language': 'en',
            'pages': [{'source_page': 1, 'render_path': str(render), 'width_pt': 400,
                       'height_pt': 500, 'pixel_width': 800, 'pixel_height': 1000}],
            'source_lines': [{'id': 'l1', 'page': 1, 'text': 'old', 'box': [30, 30, 130, 50]}],
            'blocks': [{'id': 'b1', 'page': 1, 'source_line_ids': ['l1'], 'source': 'old',
                        'translation': 'Translated', 'status': 'translated', 'action': 'replace',
                        'role': 'body', 'box': [30, 30, 300, 75], 'clean_box': [29, 29, 131, 51],
                        'background': [230, 230, 230], 'rotation': 0}]}


def test_jpeg_bytes_survive_and_only_local_region_changes(tmp_path):
    manifest = jpeg_manifest(tmp_path)
    output = tmp_path / 'out.pdf'
    report = build_scan.build_pdf(manifest, output)
    with pymupdf.open(manifest['source']) as source, pymupdf.open(output) as target:
        original = source.extract_image(source[0].get_images()[0][0])['image']
        images = [target.extract_image(x[0])['image'] for x in target[0].get_images()]
        assert original in images, 'Original JPEG was expanded into a new full-page image'
        a = np.frombuffer(source[0].get_pixmap().samples, np.uint8).reshape(500, 400, 3)
        b = np.frombuffer(target[0].get_pixmap().samples, np.uint8).reshape(500, 400, 3)
        assert np.array_equal(a[100:], b[100:])
        assert 'Translated' in target[0].get_text()
    assert output.stat().st_size < Path(manifest['source']).stat().st_size * 2
    assert report['pages'][0]['background_encoding'] == 'original_pdf_with_local_patches'


def test_hidden_ocr_removed_without_reencoding_source(tmp_path):
    manifest = jpeg_manifest(tmp_path, hidden=True)
    output = tmp_path / 'out.pdf'
    build_scan.build_pdf(manifest, output)
    with pymupdf.open(output) as target:
        assert 'old hidden source' not in target[0].get_text()
        assert any(target.extract_image(x[0])['ext'] == 'jpeg' for x in target[0].get_images())


def test_source_hash_checked_even_on_cached_repair(tmp_path):
    manifest = jpeg_manifest(tmp_path)
    build_scan.build_pdf(manifest, tmp_path / 'out.pdf')
    source = Path(manifest['source'])
    source.write_bytes(source.read_bytes() + b'\nchanged')
    with pytest.raises(ValueError, match='source PDF hash mismatch'):
        build_scan.build_pdf(manifest, tmp_path / 'out.pdf')


def test_untouched_scan_does_not_build_full_page_png(tmp_path, monkeypatch):
    manifest = jpeg_manifest(tmp_path)
    manifest['blocks'][0]['action'] = 'preserve'
    manifest['blocks'][0]['status'] = 'preserve_confirm'
    def unwanted(*args):
        raise AssertionError('Untouched encoded background should not be cleaned')
    monkeypatch.setattr(build_scan, 'prepare_clean_base', unwanted)
    out = tmp_path / 'out.pdf'
    build_scan.build_pdf(manifest, out)
    with pymupdf.open(manifest['source']) as a, pymupdf.open(out) as b:
        assert a[0].get_pixmap().samples == b[0].get_pixmap().samples


def test_channel_limit_keeps_artifact_but_blocks_delivery(tmp_path):
    manifest = jpeg_manifest(tmp_path)
    output = tmp_path / 'out.pdf'
    report = build_scan.build_pdf(manifest, output, max_output_bytes=100)
    assert output.is_file()
    assert report['delivery_ready'] is False
    assert report['size_evidence']['over_delivery_limit'] is True
    assert report['size_evidence']['output_image_stream_bytes'] > 0


def test_repair_matches_cold_and_preserves_jpeg(tmp_path):
    manifest = jpeg_manifest(tmp_path)
    output = tmp_path / 'out.pdf'
    build_scan.build_pdf(manifest, output)
    manifest['blocks'][0]['translation'] = 'Repaired'
    build_scan.build_pdf(manifest, output)
    build_scan.build_pdf(manifest, tmp_path / 'cold.pdf', use_page_cache=False)
    with pymupdf.open(output) as a, pymupdf.open(tmp_path / 'cold.pdf') as b:
        assert a[0].get_pixmap().samples == b[0].get_pixmap().samples
        assert 'Repaired' in a[0].get_text()


def test_visible_native_glyphs_use_lossless_fallback_instead_of_disappearing(tmp_path):
    manifest = jpeg_manifest(tmp_path)
    path = Path(manifest['source'])
    with pymupdf.open(path) as source:
        source[0].insert_text((30, 200), 'Original visible logo')
        changed = source.tobytes()
    path.write_bytes(changed)
    manifest['source_sha256'] = hashlib.sha256(changed).hexdigest()
    with pymupdf.open(path) as source:
        source[0].get_pixmap(matrix=pymupdf.Matrix(2, 2)).save(manifest['pages'][0]['render_path'])
    output = tmp_path / 'out.pdf'
    report = build_scan.build_pdf(manifest, output)
    assert report['pages'][0]['background_encoding'] == 'lossless_render_fallback'
    with pymupdf.open(path) as a, pymupdf.open(output) as b:
        # Original painted glyphs survive as raster pixels, not stale native text.
        clip = pymupdf.Rect(15, 180, 200, 210)
        assert a[0].get_pixmap(matrix=pymupdf.Matrix(2, 2), clip=clip).samples == b[0].get_pixmap(matrix=pymupdf.Matrix(2, 2), clip=clip).samples


def test_abnormal_growth_is_a_delivery_review_not_silent_success(tmp_path):
    source = tmp_path / 'small.pdf'
    source.write_bytes(b'x' * 1000)
    large = tmp_path / 'large.pdf'
    # A valid encoded-image PDF is used; the sparse file padding models a large
    # output without generating a large full-page raster in this unit test.
    doc = pymupdf.open()
    doc.new_page()
    doc.save(large)
    with large.open('ab') as stream:
        stream.write(b'\n%' + b'x' * (11 * 1024**2))
    evidence = build_scan.output_size_evidence({'source': str(source)}, large)
    assert evidence['size_review_required'] is True
    assert evidence['delivery_ready'] is False


def offset_jpeg_manifest(tmp_path, left, bottom):
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import RectangleObject

    manifest = jpeg_manifest(tmp_path)
    source = Path(manifest['source'])
    with PdfReader(source) as reader, PdfWriter() as writer:
        page = writer.add_page(reader.pages[0])
        page.add_transformation((1, 0, 0, 1, left, bottom))
        page.mediabox = RectangleObject([left, bottom, left + 400, bottom + 500])
        page.cropbox = RectangleObject(page.mediabox)
        data = io.BytesIO()
        writer.write(data)
    source.write_bytes(data.getvalue())
    manifest['source_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
    with pymupdf.open(source) as document:
        document[0].get_pixmap(matrix=pymupdf.Matrix(2, 2)).save(manifest['pages'][0]['render_path'])
    return manifest


def encoded_image_streams(path):
    from pypdf import PdfReader

    with PdfReader(path) as reader:
        return [obj.get_object()._data for page in reader.pages
                for obj in page['/Resources'].get('/XObject', {}).values()
                if obj.get_object().get('/Subtype') == '/Image']


@pytest.mark.parametrize('origin', [(-9, -9), (13.5, 27.25)])
def test_offset_same_boxes_preserve_saved_pixels_and_encoded_streams(tmp_path, origin):
    manifest = offset_jpeg_manifest(tmp_path, *origin)
    manifest['blocks'][0].update(action='preserve', status='preserve_confirm')
    source_bytes = Path(manifest['source']).read_bytes()
    output = tmp_path / 'normalized.pdf'
    report = build_scan.build_pdf(manifest, output)
    assert report['pages'][0]['background_encoding'] == 'original_pdf_with_local_patches'
    assert Path(manifest['source']).read_bytes() == source_bytes
    assert set(encoded_image_streams(manifest['source'])) <= set(encoded_image_streams(output))
    with pymupdf.open(manifest['source']) as source, pymupdf.open(output) as target:
        assert target[0].mediabox == pymupdf.Rect(0, 0, 400, 500)
        for dpi in (144, 200):
            matrix = pymupdf.Matrix(dpi / 72, dpi / 72)
            assert source[0].get_pixmap(matrix=matrix).samples == target[0].get_pixmap(matrix=matrix).samples


def test_offset_background_cleanup_is_aligned_at_both_render_scales(tmp_path):
    manifest = offset_jpeg_manifest(tmp_path, -9, -9)
    source_bytes = Path(manifest['source']).read_bytes()
    output = tmp_path / 'translated.pdf'
    report = build_scan.build_pdf(manifest, output)
    assert report['pages'][0]['background_encoding'] == 'original_pdf_with_local_patches'
    assert set(encoded_image_streams(manifest['source'])) <= set(encoded_image_streams(output))
    assert Path(manifest['source']).read_bytes() == source_bytes
    with pymupdf.open(manifest['source']) as source, pymupdf.open(output) as target:
        assert 'Translated' in target[0].get_text()
        for dpi in (144, 200):
            matrix = pymupdf.Matrix(dpi / 72, dpi / 72)
            a, b = (page.get_pixmap(matrix=matrix) for page in (source[0], target[0]))
            a, b = (np.frombuffer(p.samples, np.uint8).reshape(p.height, p.width, 3) for p in (a, b))
            # All cleanup and new text is above37.5pt; the rest is exact source pixels.
            assert np.array_equal(a[int(60 * dpi / 72):], b[int(60 * dpi / 72):])
            assert not np.array_equal(a[:int(40 * dpi / 72)], b[:int(40 * dpi / 72)])
        assert target[0].search_for('Translated')[0].x0 < 20


def test_offset_layout_migration_and_distinct_crop_remain_ineligible(tmp_path):
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import RectangleObject

    manifest = offset_jpeg_manifest(tmp_path, -9, -9)
    manifest['pages'][0]['layout_adjustments'] = [{'source_box': [10, 10, 20, 20]}]
    assert build_scan._source_backgrounds(manifest)[1] == {}
    manifest['pages'][0].pop('layout_adjustments')
    source = Path(manifest['source'])
    with PdfReader(source) as reader, PdfWriter() as writer:
        page = writer.add_page(reader.pages[0])
        page.mediabox = RectangleObject([-9, -9, 410, 510])
        data = io.BytesIO()
        writer.write(data)
    source.write_bytes(data.getvalue())
    manifest['source_sha256'] = hashlib.sha256(data.getvalue()).hexdigest()
    assert build_scan._source_backgrounds(manifest)[1] == {}


def test_offset_annotations_remain_ineligible(tmp_path):
    from pypdf import PdfReader, PdfWriter
    from pypdf.annotations import Text

    manifest = offset_jpeg_manifest(tmp_path, -9, -9)
    source = Path(manifest['source'])
    with PdfReader(source) as reader, PdfWriter() as writer:
        writer.add_page(reader.pages[0])
        writer.add_annotation(0, Text(rect=(50, 50, 70, 70), text='Source note'))
        data = io.BytesIO()
        writer.write(data)
    source.write_bytes(data.getvalue())
    manifest['source_sha256'] = hashlib.sha256(data.getvalue()).hexdigest()
    assert build_scan._source_backgrounds(manifest)[1] == {}


def test_normalization_leaves_reader_owned_page_unchanged(tmp_path, monkeypatch):
    manifest = offset_jpeg_manifest(tmp_path, -9, -9)
    manifest['blocks'][0].update(action='preserve', status='preserve_confirm')
    reader, bases = build_scan._source_backgrounds(manifest)
    close_reader = reader.close
    monkeypatch.setattr(reader, 'close', lambda: None)
    original = reader.pages[0]
    box = list(original.mediabox)
    content = original.get_contents().get_data()
    monkeypatch.setattr(build_scan, '_source_backgrounds', lambda manifest: (reader, bases))
    build_scan.build_pdf(manifest, tmp_path / 'out.pdf')
    assert list(original.mediabox) == box
    assert original.get_contents().get_data() == content
    close_reader()


def test_normalized_dense_vector_contents_stay_losslessly_compressed(tmp_path):
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import RectangleObject

    manifest = jpeg_manifest(tmp_path)
    source = Path(manifest['source'])
    c = canvas.Canvas(str(source), pagesize=(400, 500), pageCompression=1)
    c.translate(-9, -9)
    c.setLineWidth(.2)
    c.setStrokeColorRGB(.1, .3, .5)
    c.lines([(i % 380 + 10, 10, (i * 17) % 380 + 10, 490) for i in range(2400)])
    c.save()
    with PdfReader(source) as reader, PdfWriter() as writer:
        page = writer.add_page(reader.pages[0])
        page.mediabox = RectangleObject([-9, -9, 391, 491])
        page.cropbox = RectangleObject(page.mediabox)
        data = io.BytesIO()
        writer.write(data)
    source.write_bytes(data.getvalue())
    manifest['source_sha256'] = hashlib.sha256(data.getvalue()).hexdigest()
    manifest['blocks'][0].update(action='preserve', status='preserve_confirm')
    with pymupdf.open(source) as document:
        document[0].get_pixmap(matrix=pymupdf.Matrix(2, 2)).save(manifest['pages'][0]['render_path'])
    output = tmp_path / 'normalized.pdf'
    build_scan.build_pdf(manifest, output)
    with PdfReader(output) as reader:
        contents = reader.pages[0]['/Contents']
        streams = contents if isinstance(contents, list) else [contents]
        assert all(stream.get_object().get('/Filter') == '/FlateDecode' for stream in streams)
        assert sum(len(stream.get_object()._data) for stream in streams) < 15000
    assert output.stat().st_size < 15000, 'Unreferenced decoded contents must not be written too'
    with pymupdf.open(source) as a, pymupdf.open(output) as b:
        for dpi in (144, 200):
            matrix = pymupdf.Matrix(dpi / 72, dpi / 72)
            assert a[0].get_pixmap(matrix=matrix).samples == b[0].get_pixmap(matrix=matrix).samples


def cover_form_manifest(tmp_path, nested=False, hidden=False, large=False):
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import ArrayObject, DictionaryObject, NameObject, NumberObject

    manifest = jpeg_manifest(tmp_path)
    source = Path(manifest['source'])
    with pymupdf.open(source) as document:
        jpeg = document.extract_image(document[0].get_images()[0][0])['image']
    c = canvas.Canvas(str(source), pagesize=(400, 500), pageCompression=1)
    c.drawImage(ImageReader(io.BytesIO(jpeg)), 0, 0, width=400, height=500)
    c.setFillColorRGB(0, 0, 0)
    c.rect(30, 20, 330, 40, fill=1, stroke=0)  # Intentionally hidden footer graphic.
    c.beginForm('Cover', 0, 0, 400, 500)
    c.setFillColorRGB(1, 1, 1)
    c.rect(0, 0, 400, 80, fill=1, stroke=0)
    if large:
        c.setStrokeColorRGB(1, 1, 1)
        c.lines([(i % 380 + 10, 10, (i * 17) % 380 + 10, 70) for i in range(2400)])
    if hidden:
        text = c.beginText(20, 250)
        text.setTextRenderMode(3)
        text.textLine('hidden OCR inside Form')
        c.drawText(text)
    c.endForm()
    if nested:
        c.beginForm('Outer', 0, 0, 400, 500)
        c.doForm('Cover')
        c.endForm()
    c.doForm('Outer' if nested else 'Cover')
    c.save()
    with PdfReader(source) as reader, PdfWriter() as writer:
        page = writer.add_page(reader.pages[0])
        for reference in page['/Resources']['/XObject'].values():
            form = reference.get_object()
            if form.get('/Subtype') == '/Form':
                form[NameObject('/Matrix')] = ArrayObject([NumberObject(v) for v in (1, 0, 0, 1, 0, 0)])
                form[NameObject('/Group')] = DictionaryObject({
                    NameObject('/S'): NameObject('/Transparency'),
                    NameObject('/CS'): NameObject('/DeviceRGB')})
        data = io.BytesIO()
        writer.write(data)
    source.write_bytes(data.getvalue())
    manifest['source_sha256'] = hashlib.sha256(data.getvalue()).hexdigest()
    manifest['blocks'][0].update(action='preserve', status='preserve_confirm')
    with pymupdf.open(source) as document:
        document[0].get_pixmap(matrix=pymupdf.Matrix(2, 2)).save(manifest['pages'][0]['render_path'])
    return manifest


@pytest.mark.parametrize('nested,hidden', [(False, False), (True, False), (False, True), (True, True)])
def test_cover_form_survives_text_removal_and_reachable_page_clone(tmp_path, nested, hidden):
    manifest = cover_form_manifest(tmp_path, nested=nested, hidden=hidden)
    source = Path(manifest['source'])
    original = source.read_bytes()
    output = tmp_path / 'out.pdf'
    report = build_scan.build_pdf(manifest, output)
    assert report['pages'][0]['background_encoding'] == 'original_pdf_with_local_patches'
    assert source.read_bytes() == original
    assert set(encoded_image_streams(source)) <= set(encoded_image_streams(output))
    with pymupdf.open(source) as a, pymupdf.open(output) as b:
        assert 'hidden OCR inside Form' not in b[0].get_text()
        if hidden:
            assert 'hidden OCR inside Form' in a[0].get_text()
        for dpi in (144, 200):
            matrix = pymupdf.Matrix(dpi / 72, dpi / 72)
            assert a[0].get_pixmap(matrix=matrix).samples == b[0].get_pixmap(matrix=matrix).samples


def test_large_no_text_form_keeps_original_encoding_and_metadata(tmp_path):
    from pypdf import PdfReader

    manifest = cover_form_manifest(tmp_path, large=True)
    output = tmp_path / 'out.pdf'
    build_scan.build_pdf(manifest, output)
    with PdfReader(manifest['source']) as a, PdfReader(output) as b:
        def form(page):
            return next(ref.get_object() for ref in page['/Resources']['/XObject'].values()
                        if ref.get_object().get('/Subtype') == '/Form')
        original, saved = form(a.pages[0]), form(b.pages[0])
        assert saved._data == original._data
        assert saved.get('/Filter') == original.get('/Filter')
        for key in ('/Subtype', '/BBox', '/Matrix', '/Group'):
            assert saved[key] == original[key]
        assert '/Resources' in saved
    assert output.stat().st_size < Path(manifest['source']).stat().st_size * 2

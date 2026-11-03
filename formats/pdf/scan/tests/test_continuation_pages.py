"""Explicit overflow pages retain logical source ownership and exact target text."""
import copy
import hashlib
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from contracts import ManifestError, validate_manifest
from build_scan import build_pdf
from verify_scan import compare_geometry, extract_output_text
from scan_pagination import verify_page_numbers


def manifest(tmp_path):
    image = Image.new('RGB', (200, 200), 'white')
    ImageDraw.Draw(image).rectangle((0, 0, 199, 20), fill=(225, 225, 225))
    image_path = tmp_path / 'source.png'; image.save(image_path)
    source = tmp_path / 'source.pdf'; doc = canvas.Canvas(str(source), pagesize=(200, 200))
    doc.drawImage(ImageReader(image), 0, 0, 200, 200); doc.save()
    return {'source': str(source), 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'source_language': 'en', 'target_language': 'en', 'selected_pages': [1],
        'pages': [{'source_page': 1, 'width_pt': 200, 'height_pt': 200,
                   'pixel_width': 200, 'pixel_height': 200, 'dpi': 72, 'render_path': str(image_path)}],
        'source_lines': [{'id': 'line', 'page': 1, 'text': 'Original', 'box': [10, 40, 150, 65]}],
        'blocks': [{'id': 'body', 'page': 1, 'source_line_ids': ['line'], 'source': 'Original',
                    'translation': 'First part. Second part.', 'role': 'body', 'status': 'translated',
                    'action': 'replace', 'box': [10, 40, 70, 56], 'clean_box': [10, 40, 150, 65],
                    'max_font': 10, 'min_font': 9,
                    'segments': [{'continuation_index': 0, 'translation': 'First part. ', 'box': [10, 40, 70, 56]},
                                 {'continuation_index': 1, 'translation': 'Second part.', 'box': [10, 40, 190, 70]}]}],
        'pagination': {'reason': 'Complete prose does not fit at the source-related body size.',
            'reference_updates': {'status': 'not_present', 'reason': 'Fixture contains no TOC or internal references.'},
            'continuations': [{'source_page': 1, 'index': 1, 'body_box': [10, 30, 190, 180],
                                'repeat_regions': [{'role': 'header', 'box': [0, 0, 200, 25]}]}],
            'page_numbers': [{'source_page': 1, 'continuation_index': 0, 'text': '1', 'box': [170, 180, 198, 199]},
                             {'source_page': 1, 'continuation_index': 1, 'text': '2', 'box': [170, 180, 198, 199]}]}}


def test_segment_loss_or_duplication_is_rejected(tmp_path):
    data = manifest(tmp_path)
    data['blocks'][0]['segments'][1]['translation'] = 'Missing text'
    with pytest.raises(ManifestError, match='segment'):
        validate_manifest(data)


def test_table_flow_is_explicitly_unsupported(tmp_path):
    data = manifest(tmp_path); data['blocks'][0]['role'] = 'table_cell'
    with pytest.raises(ManifestError, match='table'):
        validate_manifest(data)


def test_builder_emits_mapped_selectable_continuation_and_original_header(tmp_path):
    data = manifest(tmp_path); out = tmp_path / 'output.pdf'
    report = build_pdf(data, out)
    result = PdfReader(out)
    assert len(result.pages) == 2
    assert 'First part.' in result.pages[0].extract_text()
    assert 'Second part.' not in result.pages[0].extract_text()
    assert 'Second part.' in result.pages[1].extract_text()
    assert report['output_page_mapping'] == [
        {'output_page': 1, 'source_page': 1, 'continuation_index': 0},
        {'output_page': 2, 'source_page': 1, 'continuation_index': 1}]


def test_verifier_uses_manifest_mapping_and_retains_both_physical_pages(tmp_path):
    data = manifest(tmp_path); out = tmp_path / 'output.pdf'; build_pdf(data, out)
    assert compare_geometry(data, PdfReader(out))
    text, _ = extract_output_text(out, [1, 1], manifest=data)
    assert 'First part.' in text[1] and 'Second part.' in text[1]


def test_running_number_is_checked_at_its_actual_output_location(tmp_path):
    data = manifest(tmp_path); out = tmp_path / 'output.pdf'; build_pdf(data, out)
    assert verify_page_numbers(data, out) == []
    data['pagination']['page_numbers'][1]['text'] = '99'
    assert 'output page 2' in verify_page_numbers(data, out)[0]


def test_header_crop_cannot_duplicate_body_text(tmp_path):
    data = manifest(tmp_path)
    data['pagination']['continuations'][0]['repeat_regions'][0]['box'] = [0,0,200,100]
    with pytest.raises(ManifestError, match='duplicate'):
        validate_manifest(data)


def test_unrequested_manifest_still_has_one_original_output_page(tmp_path):
    data = manifest(tmp_path); data.pop('pagination'); data['blocks'][0].pop('segments')
    data['blocks'][0]['box'] = [10,40,190,100]
    out = tmp_path / 'original.pdf'; result = build_pdf(data, out)
    assert len(PdfReader(out).pages) == 1 and 'output_page_mapping' not in result


def test_unsupported_internal_bookmark_remapping_is_not_silently_lost(tmp_path):
    data = manifest(tmp_path); source = Path(data['source']); changed = tmp_path/'bookmarked.pdf'
    with PdfWriter() as writer:
        writer.append(source); writer.add_outline_item('Original section',0); writer.write(changed)
    data['source'] = str(changed); data['source_sha256'] = hashlib.sha256(changed.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match='internal'):
        build_pdf(data,tmp_path/'should-not-publish.pdf')


def test_continuation_requires_measured_overflow_not_only_a_reason_string(tmp_path):
    data = manifest(tmp_path); data['blocks'][0]['box'] = [10,40,190,100]
    with pytest.raises(ValueError, match='measured overflow'):
        build_pdf(data,tmp_path/'unnecessary.pdf')


def test_running_number_binding_owns_source_id_without_duplicate_hidden_glyphs(tmp_path):
    data = manifest(tmp_path)
    data['source_lines'].append({'id':'old-number','page':1,'text':'1','box':[170,180,198,199],'rotation':0})
    data['blocks'].append({'id':'page-number','page':1,'source_line_ids':['old-number'],'source':'1',
        'translation':'1','role':'footer','status':'translated','action':'replace',
        'box':[170,180,198,199],'clean_box':[170,180,198,199],'min_font':8,'max_font':8})
    for row in data['pagination']['page_numbers']: row['block_id']='page-number'
    out=tmp_path/'bound-number.pdf'; report=build_pdf(data,out)
    assert PdfReader(out).pages[0].extract_text().split().count('1') == 1
    assert verify_page_numbers(data,out) == []
    assert any(r['id']=='page-number' for r in report['rendered_blocks'])


def test_two_ordered_segments_can_share_a_continuation_without_an_unnecessary_extra_page(tmp_path):
    data=manifest(tmp_path);b=data['blocks'][0]
    b['translation'] += ' Third part.'
    b['segments'][1]['translation'] += ' '
    b['segments'].append({'continuation_index':1,'translation':'Third part.','box':[10,90,190,120]})
    out=tmp_path/'packed.pdf';report=build_pdf(data,out);reader=PdfReader(out)
    assert len(reader.pages)==2 and 'Third part.' in reader.pages[1].extract_text()
    assert [(r['id'],r.get('segment_index')) for r in report['rendered_blocks']] == [('body',0),('body',1),('body',2)]

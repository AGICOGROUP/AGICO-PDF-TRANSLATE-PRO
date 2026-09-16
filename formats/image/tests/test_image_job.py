import copy
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'formats/pdf/scan/scripts'))
sys.path.insert(0, str(ROOT / 'formats/image/scripts'))
from compile_translation import compile_translation
from image_job import check, edit_mask, restore_untouched_pixels, import_rows, record_review
from image_pdf_bridge import sha256_file
import image_job


@pytest.mark.parametrize('size,dpi,expected', [
    ((666,841),400,0.36), ((2400,3200),400,0.18),
    ((666,841),72,1.0), ((666,841),144,1.0),
])
def test_image_ocr_does_not_reinterpret_carrier_dpi_as_source_detail(size,dpi,expected):
    assert image_job.image_ocr_scale(size,dpi) == pytest.approx(expected)


def test_inventory_uses_same_original_pixel_coordinates_as_translation_input(capsys):
    extraction = {'pages':[{'pixel_width':400,'pixel_height':600}],
                  'source_lines':[{'id':'p01-l001','text':'Label','box':[40,60,200,120]}]}
    image_job.print_inventory(extraction,{'pixel_size':[100,150]})
    assert '001\t10,15,50,30\tLabel' in capsys.readouterr().out


def fixture_data():
    extraction = {'source': 'source.pdf', 'source_sha256': 'a'*64, 'selected_pages': [1],
                  'pages': [{'source_page': 1, 'pixel_width': 100, 'pixel_height': 100,
                             'width_pt': 100, 'height_pt': 100}],
                  'source_lines': [
                      {'id': 'a', 'page': 1, 'text': 'First', 'box': [10,10,30,20], 'rotation': 0},
                      {'id': 'b', 'page': 1, 'text': 'second', 'box': [10,25,30,35], 'rotation': 0}]}
    draft = {'source_sha256': 'a'*64, 'groups': []}
    decisions = {'source_sha256': 'a'*64, 'target_language': 'zh',
                 'regions': [{'id': 'body', 'ids': ['a','b'], 'translation': '完整译文',
                              'box': [10,10,80,35]}]}
    return extraction, draft, decisions


def test_compiler_keeps_cleanup_separate_from_target_and_requires_full_ownership():
    extraction, draft, decisions = fixture_data()
    manifest = compile_translation(extraction, draft, decisions)
    assert manifest['blocks'][0]['clean_boxes'] == [[10,10,30,20], [10,25,30,35]]
    assert manifest['blocks'][0]['box'] == [10,10,80,35]
    decisions['regions'][0]['ids'] = ['a']
    with pytest.raises(ValueError):
        compile_translation(extraction, draft, decisions)


def test_compiler_rejects_stale_duplicate_and_mixed_orientation_decisions():
    extraction, draft, decisions = fixture_data()
    bad = copy.deepcopy(decisions)
    bad['source_sha256'] = 'b'*64
    with pytest.raises(ValueError):
        compile_translation(extraction, draft, bad)
    bad = copy.deepcopy(decisions)
    bad['regions'].append({'ids': ['a'], 'translation': '重复'})
    with pytest.raises(ValueError):
        compile_translation(extraction, draft, bad)
    extraction['source_lines'][1]['rotation'] = 180
    with pytest.raises(ValueError):
        compile_translation(extraction, draft, decisions)


def test_png_composition_keeps_edits_but_restores_exact_nontext_and_alpha(tmp_path):
    extraction, draft, decisions = fixture_data()
    manifest = compile_translation(extraction, draft, decisions)
    rng = np.random.default_rng(2)
    original = rng.integers(0, 256, (100,100,4), dtype=np.uint8)
    edited = original.copy()
    edited[:,:,:3] = 0  # Simulate both intended text edits and round-trip damage.
    src, dst = tmp_path/'source.png', tmp_path/'output.png'
    Image.fromarray(original).save(src)
    Image.fromarray(edited).save(dst)
    restore_untouched_pixels(src, dst, manifest, sha256_file(src))
    actual = np.asarray(Image.open(dst))
    mask = edit_mask(manifest, (100,100))
    assert np.array_equal(actual[~mask], original[~mask])
    assert np.array_equal(actual[mask], edited[mask])
    assert np.array_equal(actual[:,:,3], original[:,:,3])


def test_check_does_not_pass_without_actual_reviews_and_detects_final_pixel_damage(tmp_path):
    extraction, draft, decisions = fixture_data()
    manifest = compile_translation(extraction, draft, decisions)
    for directory in ('manifest','output'):
        (tmp_path/directory).mkdir()
    src, dst = tmp_path/'source.png', tmp_path/'out.png'
    Image.new('RGB', (100,100), 'white').save(src)
    damaged = Image.new('RGB', (100,100), 'white')
    damaged.putpixel((90,90), (0,0,0))
    damaged.save(dst)
    pdf = tmp_path/'output/translated.pdf'
    pdf.write_bytes(b'test fixture')
    (tmp_path/'source.pdf').write_bytes(b'carrier')
    manifest['source_sha256'] = sha256_file(tmp_path/'source.pdf')
    for path, value in [
        ('image-metadata.json', {'source_sha256': sha256_file(src), 'pixel_size':[100,100]}),
        ('manifest/translation-manifest.json',manifest),
        ('output/translated.build-report.json',{'output_sha256':sha256_file(pdf)})]:
        (tmp_path/path).write_text(json.dumps(value), encoding='utf-8')
    report = check(src, tmp_path, dst)
    assert not report['passed']
    assert report['pixel_check']['outside_changed_pixels'] == 1
    assert 'missing_translation-review' in report['failures']
    assert 'missing_visual-review' in report['failures']


def test_compact_rows_expand_ranges_and_original_pixel_coordinates(tmp_path):
    extraction, draft, decisions = fixture_data()
    for number,line in enumerate(extraction['source_lines'],1):
        line['id'] = f'p01-l{number:03}'
    for name,value in [('extract/extraction-report.json',extraction),
                       ('image-metadata.json',{'pixel_size':[50,50]}),
                       ('manifest/decisions.json',{'target_language':'zh'})]:
        path=tmp_path/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(value),encoding='utf-8')
    rows=tmp_path/'rows.tsv'
    rows.write_text('1-2\tbody\t完整译文\t5,5,40,20\n+label\tfooter\t名称\t5,30,20,40\tName\n',encoding='utf-8')
    import_rows(tmp_path,rows)
    result=json.loads((tmp_path/'manifest/decisions.json').read_text(encoding='utf-8'))
    manifest=compile_translation(extraction,draft,result)
    assert manifest['blocks'][0]['box'] == [10,10,80,40]
    assert manifest['blocks'][0]['clean_boxes'] == [[10,10,30,20],[10,25,30,35]]
    assert manifest['source_lines'][-1]['box'] == [10,60,40,80]


def test_review_serializer_rejects_stale_candidate_and_empty_findings(tmp_path):
    output=tmp_path/'out.png'
    Image.new('RGB',(10,10),'white').save(output)
    with pytest.raises(ValueError,match='hash'):
        record_review(tmp_path,output,'wrong','Reviewed source and target')
    with pytest.raises(ValueError,match='findings'):
        record_review(tmp_path,output,sha256_file(output),'')
    assert not (tmp_path/'review').exists()

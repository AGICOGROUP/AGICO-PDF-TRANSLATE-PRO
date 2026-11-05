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


def jpeg_build_fixture(root):
    """Fresh synthetic artwork, real compiler/builder/Poppler, no OCR or reviews."""
    from image_pdf_bridge import wrap
    root.mkdir(exist_ok=True)
    src, output = root/'source.jpg', root/'result.jpg'
    rng = np.random.default_rng(32)
    Image.fromarray(rng.integers(0, 256, (100,100,3), dtype=np.uint8)).save(src, quality=87)
    wrap(src, root/'source.pdf', root/'image-metadata.json')
    render = root/'source-render.png'
    with Image.open(src) as raw:
        raw.save(render)
    extraction, draft, decisions = fixture_data()
    for value in (extraction, draft, decisions):
        value['source_sha256'] = sha256_file(root/'source.pdf')
    extraction['source'] = str(root/'source.pdf')
    extraction['pages'][0]['render_path'] = str(render)
    decisions['target_language'] = 'en'
    decisions['regions'][0]['translation'] = 'Complete text'
    for name, value in [('extract/extraction-report.json', extraction),
                        ('manifest/draft-groups.json', draft),
                        ('manifest/decisions.json', decisions)]:
        image_job.save(root/name, value)
    return src, output


def finish_image_cli(job, output, candidate_hash=None):
    import subprocess
    return subprocess.run([
        sys.executable, str(ROOT/'formats/image/scripts/image_job.py'), 'finish',
        '--job', str(job), '--output', str(output),
        '--candidate-sha256', candidate_hash or sha256_file(output),
        '--reviewed-all-passed', '--review-note',
        'Synthetic regression fixture: review gate behavior only, not document acceptance',
    ], capture_output=True, text=True, encoding='utf-8')


def test_repeated_finish_revalidates_without_double_pausing(tmp_path):
    src, output = jpeg_build_fixture(tmp_path)
    image_job.run(ROOT/'formats/pdf/scripts/session_metrics.py', 'start', '--job', tmp_path,
                  '--source', src, '--target-language', 'en', '--mode', 'replace', '--pages', 1)
    image_job.build(tmp_path, output)
    first = finish_image_cli(tmp_path, output)
    assert first.returncode == 0, first.stderr
    frozen = (tmp_path/'session-metrics.json').read_bytes()
    second = finish_image_cli(tmp_path, output)
    assert second.returncode == 0, second.stderr
    assert (tmp_path/'session-metrics.json').read_bytes() == frozen
    # Repetition is still a real hash/evidence check, not an unconditional no-op.
    stale = finish_image_cli(tmp_path, output, '0'*64)
    assert stale.returncode != 0
    assert (tmp_path/'session-metrics.json').read_bytes() == frozen
    with Image.open(output) as raw:
        changed = raw.copy()
    changed.putpixel((95,95), (0,0,0))
    changed.save(output, format='JPEG')
    damaged = finish_image_cli(tmp_path, output)
    assert damaged.returncode != 0
    assert not image_job.read(tmp_path/'qa/final-qa.json')['passed']
    assert (tmp_path/'session-metrics.json').read_bytes() == frozen


def test_build_after_finish_resumes_same_timer_before_local_repair(tmp_path):
    src, output = jpeg_build_fixture(tmp_path)
    image_job.run(ROOT/'formats/pdf/scripts/session_metrics.py', 'start', '--job', tmp_path,
                  '--source', src, '--target-language', 'en', '--mode', 'replace', '--pages', 1)
    image_job.build(tmp_path, output)
    assert finish_image_cli(tmp_path, output).returncode == 0
    old = image_job.read(tmp_path/'session-metrics.json')
    image_job.build(tmp_path, output)
    new = image_job.read(tmp_path/'session-metrics.json')
    assert new['events'][:-1] == old['events']
    assert new['events'][-1]['action'] == 'resume'
    assert new['events'][0] == old['events'][0]
    assert finish_image_cli(tmp_path, output).returncode == 0
    assert image_job.read(tmp_path/'session-metrics.json')['events'][-1]['action'] == 'pause'


def test_finish_rejects_invalid_timer_before_writing_passing_review(tmp_path):
    src, output = jpeg_build_fixture(tmp_path)
    image_job.run(ROOT/'formats/pdf/scripts/session_metrics.py', 'start', '--job', tmp_path,
                  '--source', src, '--target-language', 'en', '--mode', 'replace', '--pages', 1)
    image_job.build(tmp_path, output)
    ledger = image_job.read(tmp_path/'session-metrics.json')
    ledger['events'][0]['active_elapsed_seconds'] = 999
    image_job.save(tmp_path/'session-metrics.json', ledger)
    result = finish_image_cli(tmp_path, output)
    assert result.returncode != 0
    assert not (tmp_path/'review/translation-review.json').exists()
    assert not (tmp_path/'qa/final-qa.json').exists()


def test_real_jpeg_build_accounts_for_encoding_without_pretending_reviews_pass(tmp_path):
    src, output = jpeg_build_fixture(tmp_path)
    image_job.build(tmp_path, output)
    report = check(src, tmp_path, output)
    pixels = report['pixel_check']
    assert pixels['outside_changed_pixels'] > 0  # The previous gate always rejected this.
    assert pixels['status'] == 'passed'
    assert pixels['composition']['lossless_outside_equal']
    assert pixels['composition']['official_edit_pixels_equal']
    assert pixels['composition']['expected_jpeg_bytes_equal']
    assert not report['passed']
    assert set(report['failures']) == {'missing_translation-review', 'missing_visual-review'}


@pytest.mark.parametrize('damage', ['final', 'composed_outside', 'composed_inside', 'manifest', 'missing'])
def test_jpeg_composition_rejects_stale_or_damaged_evidence(tmp_path, damage):
    from image_pdf_bridge import JPEG_OPTIONS
    src, output = jpeg_build_fixture(tmp_path)
    image_job.build(tmp_path, output)
    evidence_path = tmp_path/'output/image-composition.json'
    evidence = image_job.read(evidence_path)
    if damage == 'missing':
        evidence_path.unlink()
    elif damage == 'manifest':
        manifest_path = tmp_path/'manifest/translation-manifest.json'
        manifest = image_job.read(manifest_path)
        manifest['target_language'] = 'fr'
        image_job.save(manifest_path, manifest)
    elif damage == 'final':
        with Image.open(output) as raw:
            image = raw.copy()
        image.putpixel((95,95), (0,0,0))
        image.save(output, **JPEG_OPTIONS)
        # Even updating the final hash cannot bless a non-reproducible JPEG.
        evidence['candidate_sha256'] = sha256_file(output)
        image_job.save(evidence_path, evidence)
    else:
        composed = tmp_path/'output/composed.png'
        with Image.open(composed) as raw:
            image = raw.copy()
        image.putpixel((95,95) if damage.endswith('outside') else (15,15), (12,34,56))
        image.save(composed)
        image.save(output, format='JPEG', **JPEG_OPTIONS)
        # Rebinding hashes cannot hide lossless artwork/official edit damage.
        evidence['composed_sha256'] = sha256_file(composed)
        evidence['candidate_sha256'] = sha256_file(output)
        image_job.save(evidence_path, evidence)
    report = check(src, tmp_path, output)
    assert not report['passed']
    assert report['pixel_check']['status'] == 'failed'
    assert 'final_image_nontext_changes_require_review' in report['failures']


def test_prepare_rejects_any_previous_job_artifacts_before_metrics_or_source_changes(tmp_path, monkeypatch):
    job = tmp_path/'job'
    job.mkdir()
    (job/'image-metadata.json').write_text('previous task')
    monkeypatch.setattr(image_job, 'run', lambda *args: pytest.fail('Must reject before running tools'))
    with pytest.raises(ValueError, match='new job'):
        image_job.prepare(tmp_path/'source.png', job, 'en', 400)
    assert (job/'image-metadata.json').read_text() == 'previous task'


def test_build_rejects_source_overwrite_and_changed_source_before_compilation(tmp_path, monkeypatch):
    src, output = jpeg_build_fixture(tmp_path)
    monkeypatch.setattr(image_job, 'run', lambda *args: pytest.fail('Must reject before running tools'))
    original = src.read_bytes()
    with pytest.raises(ValueError, match='overwrite source'):
        image_job.build(tmp_path, src)
    assert src.read_bytes() == original
    Image.new('RGB',(100,100),'black').save(src)
    with pytest.raises(ValueError, match='Source changed'):
        image_job.build(tmp_path, output)
    assert not output.exists()


def test_failed_composition_encode_preserves_existing_candidate(tmp_path, monkeypatch):
    extraction, draft, decisions = fixture_data()
    manifest = compile_translation(extraction, draft, decisions)
    src, output = tmp_path/'source.png', tmp_path/'out.png'
    Image.new('RGB',(100,100),'white').save(src)
    Image.new('RGB',(100,100),'black').save(output)
    original = output.read_bytes()
    def fail_encode(self, path, **kwargs):
        Path(path).write_bytes(b'partial encoding')
        raise OSError('synthetic encoder failure')
    monkeypatch.setattr(Image.Image, 'save', fail_encode)
    with pytest.raises(OSError, match='encoder failure'):
        restore_untouched_pixels(src, output, manifest, sha256_file(src))
    assert output.read_bytes() == original
    assert sorted(path.name for path in tmp_path.iterdir()) == ['out.png','source.png']


def test_palette_png_transparency_survives_wrap_and_composition(tmp_path):
    from image_pdf_bridge import wrap
    src, output = tmp_path/'source.png', tmp_path/'output.png'
    image = Image.new('P', (100,100), 0)
    image.putpalette([255,255,255, 0,0,0] + [0]*762)
    image.putpixel((50,50), 1)
    image.save(src, transparency=0)
    wrap(src, tmp_path/'source.pdf', tmp_path/'image-metadata.json')
    metadata = image_job.read(tmp_path/'image-metadata.json')
    assert metadata['alpha_file']
    Image.new('RGBA', (100,100),(0,0,0,0)).save(output)
    manifest = compile_translation(*fixture_data())
    restore_untouched_pixels(src, output, manifest, sha256_file(src))
    with Image.open(output) as final:
        assert final.mode == 'RGBA'
        assert final.getpixel((50,50))[3] == 255
        assert final.getpixel((90,90))[3] == 0


def test_prepare_no_ocr_requires_visual_transcription_and_does_not_claim_no_text(tmp_path, monkeypatch, capsys):
    import extract_scan
    from PIL import ImageDraw
    def unexpected_ocr(*args, **kwargs):
        pytest.fail('Visual preparation must not initialize or call OCR')
    monkeypatch.setattr(extract_scan, 'ocr_runtime_signature', unexpected_ocr)
    monkeypatch.setattr(extract_scan, '_ocr_pass', unexpected_ocr)
    source, job = tmp_path/'source.png', tmp_path/'job'
    image = Image.new('RGB',(240,80),'white')
    ImageDraw.Draw(image).text((15,20), 'Source text requires transcription', fill='black')
    image.save(source)
    image_job.prepare(source, job, 'en', 72, run_ocr=False)
    extraction = image_job.read(job/'extract/extraction-report.json')
    context = image_job.read(job/'manifest/context.json')
    for evidence in (extraction, context):
        assert evidence['recognition_skipped'] is True
        assert evidence['reading_method'] == 'visual_required'
    assert extraction['source_lines'] == []
    assert extraction['pages'][0]['ocr_review_candidates']
    assert all(candidate['ocr_attempts'] == 0
               for candidate in extraction['pages'][0]['ocr_review_candidates'])
    assert 'visual_required' in capsys.readouterr().out
    assert not (job/'output').exists()
    assert not (job/'review').exists()
    # An empty unrecognized inventory cannot pass the manifest contract.
    with pytest.raises(ValueError, match='source_lines'):
        compile_translation(extraction, image_job.read(job/'manifest/draft-groups.json'),
                            image_job.read(job/'manifest/decisions.json'))
    rows = tmp_path/'visual.tsv'
    rows.write_text('+visual1\tbody\tLocated translation\t15,20,220,35\tVisually read source\n',encoding='utf-8')
    import_rows(job,rows)
    decisions = image_job.read(job/'manifest/decisions.json')
    assert decisions['supplements'][0]['origin'] == 'visual_supplement'
    assert decisions['supplements'][0]['box'] == [15,20,220,35]
    assert not (job/'review').exists()


def test_prepare_cli_no_ocr_flag_passes_explicit_method_and_default_stays_enabled(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(image_job, 'prepare', lambda *args, **kwargs: calls.append(kwargs))
    command = ['image_job.py','prepare','--source',str(tmp_path/'source.png'),
               '--job',str(tmp_path/'job'),'--target-language','en']
    monkeypatch.setattr(sys, 'argv', command + ['--no-ocr'])
    assert image_job.main() == 0
    monkeypatch.setattr(sys, 'argv', command)
    assert image_job.main() == 0
    assert calls == [{'run_ocr':False}, {'run_ocr':True}]

import importlib.util
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))

spec = importlib.util.spec_from_file_location('protected_source_ink', Path(__file__).parents[1] / 'scripts/protected_source_ink.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_original_numeric_ink_can_be_preserved_without_inventing_ocr_text():
    source = Image.new('RGB', (40, 40), 'white')
    source.putpixel((12, 12), (0, 0, 0))
    assert module.compare_ink(source, source.copy(), [10, 10, 20, 20]) == []


def test_even_one_modified_numeric_pixel_blocks_preservation():
    source = Image.new('RGB', (40, 40), 'white')
    target = source.copy()
    target.putpixel((12, 12), (0, 0, 0))
    assert module.compare_ink(source, target, [10, 10, 20, 20])


def test_geometry_mismatch_or_out_of_bounds_box_cannot_pass():
    source = Image.new('RGB', (40, 40), 'white')
    assert module.compare_ink(source, Image.new('RGB', (41, 40)), [10, 10, 20, 20])
    assert module.compare_ink(source, source, [-1, 10, 20, 20])


def test_ordinary_prose_cannot_use_the_protected_numeric_category():
    assert module.protection_note_errors({'disposition': 'preserved_ink', 'content_kind': 'prose', 'reason': 'clear'})
    assert module.protection_note_errors({'disposition': 'preserved_ink', 'content_kind': 'numeric', 'reason': ''})
    assert module.protection_note_errors({'disposition': 'preserved_ink', 'content_kind': 'numeric', 'reason': 'source inspected'}) == []


def test_cli_recomputes_pixels_instead_of_trusting_claimed_pass(tmp_path):
    import pymupdf

    source = tmp_path / 'source.pdf'
    target = tmp_path / 'target.pdf'
    with pymupdf.open() as doc:
        page = doc.new_page(width=100, height=100)
        page.insert_text((10, 20), '123.45')
        doc.save(source)
    with pymupdf.open(source) as doc:
        doc[0].draw_rect((10, 10, 20, 20), fill=(1, 1, 1), color=None, overlay=True)
        doc.save(target)
    candidate = {'id': 'p01-c001', 'box': [5, 5, 60, 30]}
    manifest = {'selected_pages': [1], 'pages': [{'source_page': 1, 'dpi': 72, 'pixel_width': 100, 'pixel_height': 100,
                'ocr_review_candidates': [candidate]}]}
    note = {'source_id': 'p01-c001', 'disposition': 'preserved_ink',
            'content_kind': 'numeric', 'reason': 'Source numeric value inspected',
            'pixel_check_passed': True}
    review = {'pages': [{'corrections': [note]}]}
    assert module.validate_protected_ink(review, manifest, source, source, tmp_path / 'equal') == []
    assert any('modified' in e for e in module.validate_protected_ink(
        review, manifest, source, target, tmp_path / 'changed'))


def test_wrong_dpi_cannot_move_protection_crop_to_blank_area(tmp_path):
    import pymupdf

    source = tmp_path / 'source.pdf'
    target = tmp_path / 'target.pdf'
    with pymupdf.open() as doc:
        page = doc.new_page(width=100, height=100)
        page.insert_text((45, 50), '123.45', fontsize=8)
        doc.save(source)
    with pymupdf.open(source) as doc:
        doc[0].draw_rect((40, 35, 80, 60), fill=(1, 1, 1), color=None, overlay=True)
        doc.save(target)
    candidate = {'id': 'number', 'box': [40, 35, 80, 60]}
    manifest = {'selected_pages': [1], 'pages': [{'source_page': 1, 'dpi': 144,
                'pixel_width': 100, 'pixel_height': 100,
                'ocr_review_candidates': [candidate]}]}
    review = {'pages': [{'corrections': [{'source_id': 'number',
               'disposition': 'preserved_ink', 'content_kind': 'numeric',
               'reason': 'Visible source number'}]}]}
    errors = module.validate_protected_ink(review, manifest, source, target, tmp_path / 'check')
    assert any('manifest pixel' in error for error in errors)


def test_missing_pixel_contract_cannot_pass(tmp_path):
    import pymupdf

    source = tmp_path / 'source.pdf'
    with pymupdf.open() as doc:
        doc.new_page(width=100, height=100)
        doc.save(source)
    manifest = {'selected_pages': [1], 'pages': [{'source_page': 1, 'dpi': 72,
                'ocr_review_candidates': [{'id': 'n', 'box': [1, 1, 10, 10]}]}]}
    review = {'pages': [{'corrections': [{'source_id': 'n', 'disposition': 'preserved_ink',
               'content_kind': 'numeric', 'reason': 'Inspected'}]}]}
    assert module.validate_protected_ink(review, manifest, source, source, tmp_path / 'check')


def test_target_pixel_size_must_match_manifest_even_if_crop_is_unchanged(tmp_path):
    import pymupdf

    source, target = tmp_path / 'source.pdf', tmp_path / 'target.pdf'
    for path, width in [(source, 100), (target, 101)]:
        with pymupdf.open() as doc:
            doc.new_page(width=width, height=100)
            doc.save(path)
    manifest = {'selected_pages': [1], 'pages': [{'source_page': 1, 'dpi': 72,
                'pixel_width': 100, 'pixel_height': 100,
                'ocr_review_candidates': [{'id': 'n', 'box': [1, 1, 10, 10]}]}]}
    review = {'pages': [{'corrections': [{'source_id': 'n', 'disposition': 'preserved_ink',
               'content_kind': 'numeric', 'reason': 'Inspected'}]}]}
    errors = module.validate_protected_ink(review, manifest, source, target, tmp_path / 'check')
    assert any('manifest pixel' in error for error in errors)

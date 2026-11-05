"""Language-pair scope must not substitute CJK detection for translation review."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from compile_translation import compile_translation
from verify_scan import requires_cjk_residual_gate


@pytest.mark.parametrize('source,target,expected', [
    ('zh', 'en', True), ('zh-CN', 'en-US', True),
    ('en', 'zh', False), ('en-US', 'zh-CN', False),
    ('es', 'en', False), ('fr', 'en', False), ('pt-BR', 'en', False),
    ('ru', 'en', False), ('tr', 'en', False),
    ('en', 'es', False), ('en', 'ru', False),
    ('', 'en', True), ('unknown', 'en', True),
])
def test_residual_gate_uses_actual_language_pair(source, target, expected):
    assert requires_cjk_residual_gate(target, source, [{'text': 'Readable source'}]) is expected


def test_observed_chinese_overrides_non_chinese_source_declaration():
    assert requires_cjk_residual_gate('en', 'en', [{'text': 'Power 功率'}])
    assert requires_cjk_residual_gate('en')  # Conservative legacy behavior.


def inputs():
    extraction = {'source': 'source.pdf', 'source_sha256': 'a'*64, 'selected_pages': [1],
        'pages': [{'source_page': 1, 'pixel_width': 100, 'pixel_height': 100,
                   'width_pt': 100, 'height_pt': 100}],
        'source_lines': [{'id': 'a', 'page': 1, 'text': '功率', 'box': [10,10,30,20], 'rotation': 0}]}
    return extraction, {'source_sha256': 'a'*64, 'groups': []}, {
        'source_sha256': 'a'*64, 'source_language': 'zh-CN', 'target_language': 'en',
        'regions': [{'id': 'body', 'ids': ['a'], 'translation': 'Power', 'box': [10,10,80,35]}]}


def test_compiler_retains_source_language_and_rejects_conflicting_binding():
    extraction, draft, decisions = inputs()
    assert compile_translation(extraction, draft, decisions)['source_language'] == 'zh-CN'
    extraction['source_language'] = 'es'
    with pytest.raises(ValueError, match='source language'):
        compile_translation(extraction, draft, decisions)


@pytest.mark.parametrize('bad', [123, '', '   '])
def test_compiler_rejects_invalid_source_language_metadata(bad):
    extraction, draft, decisions = inputs()
    decisions['source_language'] = bad
    with pytest.raises(ValueError, match='source language'):
        compile_translation(extraction, draft, decisions)


def test_source_language_regions_are_compatible_and_missing_legacy_metadata_allowed():
    extraction, draft, decisions = inputs()
    extraction['source_language'] = ' zh '
    assert compile_translation(extraction, draft, decisions)['source_language'] == 'zh-CN'
    decisions.pop('source_language')
    extraction.pop('source_language')
    assert 'source_language' not in compile_translation(extraction, draft, decisions)

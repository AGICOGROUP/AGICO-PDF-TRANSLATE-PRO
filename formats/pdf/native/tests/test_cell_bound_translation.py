import argparse
import importlib.util
import json
import sys
from pathlib import Path

from reportlab.pdfgen import canvas

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_positioned_word_spaces_and_tight_identifier():
    pipeline = load('pdf_translation_pipeline')
    chars = []
    x = 0
    for word in ('Hog', 'fuel', 'details', 'missing'):
        for letter in word:
            chars.append(dict(text=letter, x0=x, x1=x + 5, size=10))
            x += 5
        x += 2.2
    assert pipeline.text_from_chars(chars) == 'Hog fuel details missing'
    assert pipeline.text_from_chars([dict(text='A', x0=0, x1=5, size=10),
                                     dict(text='1', x0=5.4, x1=10, size=10)]) == 'A1'


def test_extract_cells_before_translation_and_wrap_without_line_binding(tmp_path):
    pipeline = load('pdf_translation_pipeline')
    rebuild = load('native_selectable_rebuild')
    source = tmp_path / 'source.pdf'
    pdf = canvas.Canvas(str(source), pagesize=(400, 400))
    pdf.setFont('Helvetica', 10)
    for x in (20, 70, 300, 380):
        pdf.line(x, 200, x, 260)
    for y in (200, 230, 260):
        pdf.line(20, y, 380, y)
    pdf.drawString(25, 248, '1')
    pdf.drawString(75, 248, 'Hog fuel details missing')
    pdf.drawString(75, 236, '(moisture not confirmed)')
    pdf.drawString(305, 248, 'Resolved')
    pdf.drawString(25, 218, '2')
    pdf.drawString(75, 218, 'Water supply')
    pdf.drawString(305, 218, 'Pending')
    pdf.save()
    manifest = tmp_path / 'manifest.json'
    pipeline.extract_command(argparse.Namespace(input=source, manifest=manifest,
                                                source_language='en', target_language='zh'))
    data = json.loads(manifest.read_text(encoding='utf8'))
    page = data['pages'][0]
    assert len(page['blocks']) == 6
    prose = next(b for b in page['blocks'] if 'Hog' in b['source_text'])
    assert prose['source_text'] == 'Hog fuel details missing\n(moisture not confirmed)'
    assert prose['translation'] == ''
    assert 'Resolved' not in prose['source_text']
    for b in page['blocks']:
        b['translation'] = '中文译文'
    prose['translation'] = '缺少碎木燃料数据（水分未确认）'
    pipeline.enrich_manifest_layout(source, data)
    flows, ids = rebuild.build_table_cell_render_plan(page, pipeline)
    assert len(flows) == 6
    assert ids == {b['id'] for b in page['blocks']}
    assert any(f['text'] == prose['translation'] for f in flows)
    # Extra target wrapping remains in the same cell rather than a legacy fallback.
    prose['translation'] = '第一行\n第二行\n第三行'
    flows, ids = rebuild.build_table_cell_render_plan(page, pipeline)
    assert len(flows) == 6
    assert prose['id'] in ids
    assert sum(prose['id'] in f['block_ids'] for f in flows) == 1
    # Cell splitting preserves every visible source glyph exactly once.
    extracted = ''.join(c['text'] for b in page['blocks'] for c in b['characters'])
    import pdfplumber
    with pdfplumber.open(source) as pdf:
        original = ''.join(c['text'] for c in pdf.pages[0].chars if pipeline.visible_character(c))
    from collections import Counter
    assert Counter(extracted) == Counter(original)


def test_cell_evidence_rejects_duplicate_misplaced_or_lost_text():
    pipeline = load('pdf_translation_pipeline')
    verifier = load('verify_native_typography')
    block_id = 'p0001-b0001'
    blocks = {block_id: {'source_cell_bbox': [0, 0, 100, 30], 'translation': '完整译文'}}
    draw = {'rendered': '完整译文', 'drawn_boxes': [[2, 2, 80, 20]]}
    report = {'blocks': [{'id': 'cell:' + block_id, 'draws': [draw]}]}
    assert verifier.bound_cell_failures(blocks, report, pipeline) == []
    draw['rendered'] = '译文'
    assert verifier.bound_cell_failures(blocks, report, pipeline)
    draw['rendered'] = '完整译文'
    draw['drawn_boxes'][0][2] = 110
    assert verifier.bound_cell_failures(blocks, report, pipeline)
    draw['drawn_boxes'][0][2] = 80
    report['blocks'][0]['draws'].append(draw)
    assert verifier.bound_cell_failures(blocks, report, pipeline)


def test_vertical_dash_rule_uses_single_render_mark():
    pipeline = load('pdf_translation_pipeline')
    block = {'source_text': '-----', 'translation': '-----',
             'bbox': [10, 10, 11.5, 40], 'lines': []}
    assert pipeline.prepared_translation(block) == '—'


def test_fragmented_light_diagram_labels_are_regrouped_by_character_baseline():
    pipeline = load('pdf_translation_pipeline')

    def char(text, x0, top):
        return {
            'text': text, 'x0': x0, 'x1': x0 + 4, 'top': top,
            'bottom': top + 8.5, 'size': 8.5, 'width': 4,
            'fontname': 'Helvetica', 'non_stroking_color': (1.0,),
            'matrix': (1, 0, 0, 1, 0, 0),
        }

    pellet = [char(letter, 100 + index * 4, 50) for index, letter in enumerate('Pelletizing')]
    system = [char(letter, 104 + index * 4, 60.3) for index, letter in enumerate('System')]
    # Reproduce pdfplumber's interleaved fragments: one raw line contains
    # characters from two visual baselines while adjacent letters are split.
    raw_lines = [
        {'chars': pellet[:1], 'x0': 100, 'x1': 104, 'top': 50, 'bottom': 58.5},
        {'chars': [pellet[1], system[0]], 'x0': 104, 'x1': 108, 'top': 50, 'bottom': 68.8},
        {'chars': pellet[2:-1], 'x0': 108, 'x1': 136, 'top': 50, 'bottom': 58.5},
        {'chars': system[1:], 'x0': 108, 'x1': 128, 'top': 60.3, 'bottom': 68.8},
        {'chars': pellet[-1:], 'x0': 136, 'x1': 140, 'top': 50, 'bottom': 58.5},
    ]

    repaired = pipeline.regroup_light_diagram_lines(raw_lines)
    texts = [pipeline.text_from_chars(line['chars']) for line in repaired]
    assert texts == ['Pelletizing', 'System']


def test_adjacent_same_baseline_diagram_title_fragments_are_coalesced():
    pipeline = load('pdf_translation_pipeline')

    def fragment(text, x0):
        chars = []
        x = x0
        for letter in text:
            chars.append({
                'text': letter, 'x0': x, 'x1': x + 4, 'top': 50,
                'bottom': 58.5, 'size': 8.5, 'width': 4,
                'fontname': 'Helvetica', 'non_stroking_color': (0,),
                'matrix': (1, 0, 0, 1, 0, 0),
            })
            x += 4
        return {'chars': chars, 'x0': x0, 'x1': x, 'top': 50, 'bottom': 58.5}

    raw = [fragment('BLAC', 100), fragment('K', 116), fragment('WOOD', 120)]
    repaired = pipeline.coalesce_inline_fragments(raw)
    assert len(repaired) == 1
    assert pipeline.text_from_chars(repaired[0]['chars']) == 'BLACKWOOD'


def test_cjk_target_keeps_math_only_blocks_on_symbol_capable_font():
    rebuild = load('native_selectable_rebuild')
    manifest = {
        'target_language': 'zh',
        'pages': [{'blocks': [
            {'translation': '中文', 'style': {}},
            {'translation': 'U0001d45dℎ', 'style': {}},
        ]}],
    }
    rebuild.mark_cjk_styles(manifest)
    assert manifest['pages'][0]['blocks'][0]['style']['cjk'] is True
    assert manifest['pages'][0]['blocks'][1]['style'].get('cjk') is not True


def test_compact_standalone_mark_does_not_lose_horizontal_box_to_padding():
    rebuild = load('native_selectable_rebuild')
    assert rebuild.text_box_horizontal_padding('•') == 0.0
    assert rebuild.fallback_minimum_scale('•') == 0.25
    assert rebuild.text_box_horizontal_padding('中文译文') == 1.0
    assert rebuild.fallback_minimum_scale('中文译文') == 0.45


def test_force_block_mode_uses_full_block_box_not_first_protected_fragment():
    rebuild = load('native_selectable_rebuild')
    block = {
        'id': 'p0001-b0001', 'bbox': [100, 50, 240, 60],
        'role': 'body-9', 'force_block_mode': True,
        'style': {'size': 9, 'role_size': 9, 'align': 0},
    }
    line = {
        'bbox': [100, 50, 120, 60],
        'characters': [{'protected': True}],
    }
    page = {
        'width': 400, 'height': 400, 'content_bounds': [40, 360],
        'blocks': [block], 'table_cells': [], 'image_boxes': [],
    }
    reference = rebuild.block_mode_reference_line(block, [line])
    assert rebuild.resolve_text_container(page, block, reference)[2] >= 240


def test_rotated_image_label_wraps_at_full_width_parenthesis():
    overlay = load('apply_image_vector_text')
    assert overlay.rotated_label_lines('阿莫希亚路（未成形）') == [
        '阿莫希亚路', '（未成形）'
    ]


def test_selectability_content_count_ignores_decorative_dot_leaders():
    verifier = load('verify_selectable_output')
    assert verifier.content_character_count('目录......34') == verifier.content_character_count('目录34')
    assert verifier.content_character_count('压力 3.5 bar') > verifier.content_character_count('压力 bar')

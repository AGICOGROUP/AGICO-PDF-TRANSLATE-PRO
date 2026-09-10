import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cad_batch import cell_proposals, merge_supplement


def test_review_bundle_is_bound_to_source_and_candidate_and_cached(tmp_path):
    import cad_batch
    source, candidate = tmp_path/'source.pdf', tmp_path/'target.pdf'
    with pymupdf.open() as doc:
        page = doc.new_page(width=200,height=100)
        page.insert_text((20,30),'Silo')
        doc.save(source)
        page.insert_text((20,60),'Target')
        doc.save(candidate)
    records = [dict(id='label',page=0,source='Silo',translation='Target',bbox=[20,10,100,70])]
    out = tmp_path/'review'
    first = cad_batch.review_bundle(source,out,records,candidate,'hash1')
    second = cad_batch.review_bundle(source,out,records,candidate,'hash1')
    assert second['cache_hit'] is True
    assert first['regions'] == ['label']
    records[0]['translation'] = 'Different'
    third = cad_batch.review_bundle(source,out,records,candidate,'hash1')
    assert third['cache_hit'] is False
    (out/'region-0-source.png').write_bytes(b'corrupt')
    assert cad_batch.review_bundle(source,out,records,candidate,'hash1')['cache_hit'] is False


def test_cell_is_inset_and_shared_description_is_not_auto_approved():
    with pymupdf.open() as doc:
        page = doc.new_page(width=400, height=200)
        page.draw_rect([20, 20, 300, 100])
        page.draw_line((20, 60), (300, 60))
        records = [dict(id='a', bbox=[30, 32, 180, 48]),
                   dict(id='b', bbox=[200, 32, 240, 48])]
        proposals = cell_proposals(page, records)
        assert proposals['a']['cell_bbox'] == [20., 20., 300., 60.]
        assert proposals['a']['layout_box'][0] > 20
        assert proposals['a']['members'] == ['a', 'b']
        assert 'approved' not in proposals['a']


def test_open_pipes_are_not_a_table_cell():
    with pymupdf.open() as doc:
        page = doc.new_page(width=400, height=200)
        page.draw_line((20, 20), (300, 20))
        page.draw_line((20, 60), (300, 60))
        assert not cell_proposals(page, [dict(id='a', bbox=[30, 32, 100, 48])])


def test_shared_cell_fields_receive_separate_layouts():
    with pymupdf.open() as doc:
        page = doc.new_page(width=400, height=200)
        page.draw_rect([20, 20, 300, 100])
        records = [dict(id='a', bbox=[30, 32, 100, 48]),
                   dict(id='b', bbox=[200, 32, 240, 48])]
        proposals = cell_proposals(page, records)
        assert proposals['a']['layout_box'][2] <= proposals['b']['layout_box'][0]
        records[1]['bbox'] = [30, 70, 100, 85]
        proposals = cell_proposals(page, records)
        assert proposals['a']['layout_box'][3] <= proposals['b']['layout_box'][1]


def test_image_structure_ignores_unused_resources_but_detects_moved_image(tmp_path):
    import native_cad_pipeline as cad
    with pymupdf.open() as doc:
        page = doc.new_page(width=200, height=100)
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 3, 3), False)
        pix.clear_with(100)
        page.insert_image([20, 20, 40, 40], pixmap=pix)
        expected = cad.page_snapshot(page)
        equivalent = dict(expected, image_count=99)
        assert cad.same_page_structure(expected, equivalent)
        with pymupdf.open() as other:
            target = other.new_page(width=200, height=100)
            target.insert_image([30, 20, 50, 40], pixmap=pix)
            assert not cad.same_page_structure(expected, cad.page_snapshot(target))
        assert not cad.same_page_structure(expected, dict(expected, painted_images=[]))


def test_path_merging_preserves_pixels_despite_lower_vector_count():
    import native_cad_pipeline as cad
    with pymupdf.open() as source, pymupdf.open() as candidate:
        original = source.new_page(width=200, height=100)
        target = candidate.new_page(width=200, height=100)
        original.draw_line((10, 20), (100, 20))
        original.draw_line((10, 40), (100, 40))
        shape = target.new_shape()
        shape.draw_line((10, 20), (100, 20))
        shape.draw_line((10, 40), (100, 40))
        shape.finish(color=(0, 0, 0))
        shape.commit()
        expected, actual = cad.page_snapshot(original), cad.page_snapshot(target)
        assert actual['vector_count'] < expected['vector_count']
        assert original.get_pixmap().samples == target.get_pixmap().samples
        assert cad.same_page_structure(expected, actual)
        assert not cad.same_page_structure(expected, dict(actual, width=300))


def test_displaylist_review_crops_match_page_render(tmp_path):
    import cad_batch
    source = tmp_path/'source.pdf'
    with pymupdf.open() as doc:
        page = doc.new_page(width=200, height=100)
        page.insert_text((20, 30), 'Dimension 300')
        page.draw_line((10, 40), (190, 40), color=(1, 0, 0))
        doc.save(source)
    records = [dict(id='a', page=0, source='Dimension 300', bbox=[20, 10, 120, 45])]
    cad_batch.review_bundle(source, tmp_path/'review', records)
    with pymupdf.open(source) as doc:
        expected = doc[0].get_pixmap(matrix=pymupdf.Matrix(2, 2), clip=[12, 2, 128, 53], alpha=False)
        actual = pymupdf.Pixmap(str(tmp_path/'review/region-0-source.png'))
        assert expected.samples == actual.samples


def test_supplement_keeps_existing_ids_and_adds_only_missing_regions():
    existing = [dict(id='p0001-o00001', page=0, source='Vent', bbox=[10, 10, 30, 30])]
    proposals = [dict(source='Vent', bbox=[11, 11, 31, 31]),
                 dict(source='Feed Hopper', bbox=[100, 100, 150, 120])]
    result = merge_supplement(existing, proposals, [], 0)
    assert len(result) == 1
    assert result[0]['id'] == 'p0001-u00001'
    assert existing[0]['id'] == 'p0001-o00001'


def test_small_native_token_does_not_hide_supplemental_description():
    native = [dict(page=0,bbox=[10,10,12,12],source='M')]
    found = [dict(source='Motor station',bbox=[9,9,80,30])]
    assert len(merge_supplement([],found,native,0)) == 1


def test_small_outline_token_does_not_hide_supplemental_description():
    existing = [dict(id='p0001-o00001', page=0, source='M', bbox=[10,10,12,12])]
    found = [dict(source='Motor station', bbox=[9,9,80,30])]
    assert len(merge_supplement(existing, found, [], 0)) == 1


def test_prepare_resume_preserves_manual_records_and_context(tmp_path):
    import native_cad_pipeline as cad
    source = tmp_path/'source.pdf'
    with pymupdf.open() as doc:
        doc.new_page(width=200, height=100).insert_text((20,30), 'Silo')
        doc.save(source)
    job = tmp_path/'job'
    assert cad.prepare(source, job) == 0
    inventory = cad.read_json(job/cad.INVENTORY_NAME)
    packet = cad.read_json(job/cad.PACKET_NAME)
    manual = dict(id='p0001-m00001', page=0, source='Vent', bbox=[20,50,60,65],
                  kind='outline', status='pending', rotation=0, color=0, font_size=10)
    inventory['records'].append(manual)
    translated = dict(manual, status='translated', translation='Exhaust',
                      cover_review={'approved': True, 'note': 'Manually inspected'})
    packet['records'].append(translated)
    cad.write_json(job/cad.INVENTORY_NAME, inventory)
    cad.write_json(job/cad.PACKET_NAME, packet)
    for _ in range(2):
        assert cad.prepare(source, job) == 0
        resumed = cad.read_json(job/cad.PACKET_NAME)
        matches = [r for r in resumed['records'] if r['id'] == manual['id']]
        assert len(matches) == 1
        assert all(matches[0][key] == value for key, value in translated.items())
        assert {'id': manual['id'], 'source': 'Vent'} in resumed['page_context'][0]['records']


def test_review_version_rebuild_reuses_ocr_cache(tmp_path, monkeypatch):
    import cad_batch
    import rapidocr_onnxruntime
    calls = []
    def engine(*args):
        calls.append(True)
        return [], None
    monkeypatch.setattr(rapidocr_onnxruntime, 'RapidOCR', lambda: engine)
    source = tmp_path/'source.pdf'
    with pymupdf.open() as doc:
        doc.new_page(width=200, height=100)
        doc.save(source)
    out = tmp_path/'review'
    args = (source, out, [], source, 'same-hash', 'cjk')
    assert cad_batch.review_bundle(*args)['cache_hit'] is False
    assert cad_batch.review_bundle(*args)['cache_hit'] is True
    monkeypatch.setattr(cad_batch, 'REVIEW_CACHE_VERSION', 'test-next-version', raising=False)
    assert cad_batch.review_bundle(*args)['cache_hit'] is False
    assert cad_batch.review_bundle(*args)['cache_hit'] is True
    assert len(calls) == 1


def test_resume_rejects_other_source_inventory_without_packet(tmp_path):
    import native_cad_pipeline as cad
    source = tmp_path/'source.pdf'
    with pymupdf.open() as doc:
        doc.new_page(width=200, height=100)
        doc.save(source)
    job = tmp_path/'job'
    assert cad.prepare(source, job) == 0
    (job/cad.PACKET_NAME).unlink()
    inventory = cad.read_json(job/cad.INVENTORY_NAME)
    inventory['source_sha256'] = 'another-source'
    cad.write_json(job/cad.INVENTORY_NAME, inventory)
    before = (job/cad.INVENTORY_NAME).read_bytes()
    assert cad.prepare(source, job) == 2
    assert (job/cad.INVENTORY_NAME).read_bytes() == before


def test_restore_uses_each_pages_own_paths(tmp_path):
    import native_cad_pipeline as cad
    source = tmp_path/'input.pdf'
    with pymupdf.open() as doc:
        for y in (32,38):
            page = doc.new_page(width=200,height=100)
            page.draw_line((25,25),(30,30))
            page.draw_line((0,y),(200,y))
        doc.save(source)
    job=tmp_path/'job'
    assert cad.prepare(source,job) == 0
    inventory=cad.read_json(job/cad.INVENTORY_NAME)
    packet=cad.read_json(job/cad.PACKET_NAME)
    for page in (0,1):
        record=dict(id=f'p{page}-outline',source='Silo',page=page,bbox=[20,20,75,45],
                    kind='outline',status='pending',font_size=8,color=0,rotation=0)
        inventory['records'].append(record)
        packet['records'].append(dict(record,status='translated',translation='Silo',
            cover_review=dict(approved=True,text_only=True,white_background=True,
                              restore_conflicting_paths=True,note='Inspected straight crossing pipe.')))
    cad.write_json(job/cad.INVENTORY_NAME,inventory)
    cad.write_json(job/cad.PACKET_NAME,packet)
    assert cad.apply(job,job/cad.PACKET_NAME,cad.DEFAULT_FONT) == 0
    with pymupdf.open(job/cad.OUTPUT_NAME) as doc:
        for index,y in enumerate((32,38)):
            pix=doc[index].get_pixmap(matrix=pymupdf.Matrix(4,4),clip=[60,y-.5,65,y+.5])
            assert min(pix.samples) < 40

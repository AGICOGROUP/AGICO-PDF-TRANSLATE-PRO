import json
import pytest
from formats.pdf.native.tests.test_run_v6_job import prepare_annotation_job, run


@pytest.mark.parametrize('complete', [True, False])
def test_canonical_annotation_inputs_do_not_copy_onto_themselves(tmp_path, complete):
    job, image_id = prepare_annotation_job(tmp_path)
    metadata = job / 'image-vector-metadata.json'
    review = job / 'image-review.json'
    metadata.write_text(json.dumps({'images': []}), encoding='utf-8')
    payload = {'complete': complete, 'reviewed_image_ids': [image_id], 'images': [{
        'id': image_id, 'contains_source_text': False, 'expected_label_count': 0,
        'translated_label_count': 0, 'preserved_label_count': 0,
        'confirm_count': 0, 'labels': []}]}
    review.write_text(json.dumps(payload), encoding='utf-8')
    original = (metadata.read_bytes(), review.read_bytes())
    result = run('annotate-images', job, '--metadata', metadata, '--review', review)
    if complete:
        assert result.returncode == 0, result.stderr
        assert json.loads((job/'job.json').read_text())['stage'] == 'images_annotated'
    else:
        assert result.returncode != 0
        assert 'image review is incomplete' in result.stderr
    assert original == (metadata.read_bytes(), review.read_bytes())

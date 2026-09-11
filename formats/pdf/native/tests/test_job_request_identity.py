import json
import subprocess
import sys
from pathlib import Path

import pymupdf
import pytest


RUNNER = Path(__file__).resolve().parents[1] / 'scripts' / 'run_v6_job.py'


def invoke(*args):
    return subprocess.run([sys.executable, str(RUNNER), *map(str, args)],
                          capture_output=True, text=True, encoding='utf-8')


def init(source, root, target, *extra):
    result = invoke('init', source, '--jobs-root', root,
                    '--source-language', 'es', '--target-language', target, *extra)
    assert result.returncode == 0, result.stderr
    return Path(json.loads(result.stdout)['job_dir'])


def source_pdf(tmp_path):
    path = tmp_path / 'source.pdf'
    with pymupdf.open() as doc:
        doc.new_page().insert_text((30, 50), 'VISTA INFERIOR')
        doc.save(path)
    return path


def test_different_target_does_not_reuse_manifest(tmp_path):
    source = source_pdf(tmp_path)
    english = init(source, tmp_path / 'jobs', 'en')
    before = (english / 'manifest.json').read_bytes()
    chinese = init(source, tmp_path / 'jobs', 'zh-CN')
    assert english != chinese
    assert json.loads((chinese / 'manifest.json').read_text('utf-8'))['target_language'] == 'zh-CN'
    assert (english / 'manifest.json').read_bytes() == before


def test_same_intent_resumes_but_fresh_preserves_old_job(tmp_path):
    source = source_pdf(tmp_path)
    job = init(source, tmp_path / 'jobs', 'zh-CN')
    manifest_path = job / 'manifest.json'
    manifest = json.loads(manifest_path.read_text('utf-8'))
    manifest['pages'][0]['blocks'][0]['translation'] = 'existing translation'
    manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
    before = manifest_path.read_bytes()
    assert init(source, tmp_path / 'jobs', 'ZH_cn') == job
    assert manifest_path.read_bytes() == before
    fresh = init(source, tmp_path / 'jobs', 'zh-CN', '--fresh')
    assert fresh != job
    assert manifest_path.read_bytes() == before
    assert 'existing translation' not in (fresh / 'manifest.json').read_text('utf-8')
    assert json.loads((fresh / 'job.json').read_text('utf-8'))['stage'] == 'initialized'


@pytest.mark.parametrize('operation', ['init', 'build-native'])
def test_changed_manifest_language_is_not_silently_rebound(tmp_path, operation):
    source = source_pdf(tmp_path)
    job = init(source, tmp_path / 'jobs', 'zh-CN')
    path = job / 'manifest.json'
    manifest = json.loads(path.read_text('utf-8'))
    manifest['target_language'] = 'en'
    for page in manifest['pages']:
        for block in page['blocks']:
            block['translation'] = 'View'
    path.write_text(json.dumps(manifest), encoding='utf-8')
    before = (job / 'job.json').read_bytes()
    result = (invoke('init', source, '--jobs-root', tmp_path / 'jobs',
                     '--source-language', 'es', '--target-language', 'zh-CN')
              if operation == 'init' else invoke(operation, job))
    assert result.returncode != 0
    assert 'language' in result.stderr.lower()
    assert (job / 'job.json').read_bytes() == before

"""Fresh per-page OCR caches must invalidate without skipping actual QA review."""
from pathlib import Path
import sys
from types import SimpleNamespace

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import verify_scan


def test_residual_ocr_reuses_only_unchanged_pages_and_runtime(tmp_path, monkeypatch):
    pdf = tmp_path/'candidate.pdf'
    pdf.write_bytes(b'fresh synthetic PDF renderer input')
    revision = {'model': 1, 'page2': 0}
    calls = []
    engines = []
    def render(command, **kwargs):
        prefix = Path(command[-1])
        prefix.parent.mkdir(parents=True, exist_ok=True)
        for page in [1, 2]:
            Image.new('RGB', (30, 20), (revision['page2'] if page == 2 else 0, 0, 0)).save(
                prefix.with_name(prefix.name+f'-{page}.png'))
    def recognize(engine, image, scale):
        calls.append(scale)
        return [{'text': '未译', 'box': [1,1,8,8], 'score': 0.9, 'rotation': 0, 'scale': scale}]
    monkeypatch.setattr(verify_scan.subprocess, 'run', render)
    monkeypatch.setattr(verify_scan, 'find_pdftoppm', lambda: 'fixture-renderer')
    monkeypatch.setattr(verify_scan, 'ocr_runtime_signature', lambda: {'model': revision['model']}, raising=False)
    monkeypatch.setattr(verify_scan, '_ocr_pass', recognize)
    monkeypatch.setitem(sys.modules, 'rapidocr_onnxruntime', SimpleNamespace(
        RapidOCR=lambda: engines.append(object()) or engines[-1]))
    directory = tmp_path/'qa'
    first = verify_scan.residual_cjk_ocr(pdf, directory, [4, 9])
    assert len(calls) == 4
    assert verify_scan.residual_cjk_ocr(pdf, directory, [4, 9]) == first
    assert len(calls) == 4 and len(engines) == 1
    pdf.write_bytes(b'new candidate: only page two changed')
    revision['page2'] = 1
    assert verify_scan.residual_cjk_ocr(pdf, directory, [4, 9]) == first
    assert len(calls) == 6
    revision['model'] = 2
    verify_scan.residual_cjk_ocr(pdf, directory, [4, 9])
    assert len(calls) == 10
    # An unreadable cache is a local miss, never accepted as zero residue.
    caches = sorted((directory/'ocr-checkpoints').glob('*.json'))
    assert len(caches) == 2
    caches[0].write_text('{broken', encoding='utf-8')
    assert verify_scan.residual_cjk_ocr(pdf, directory, [4, 9]) == first
    assert len(calls) == 12
    remapped = verify_scan.residual_cjk_ocr(pdf, directory, [9, 4])
    assert [item['source_page'] for item in remapped] == [9, 4]
    assert len(calls) == 16

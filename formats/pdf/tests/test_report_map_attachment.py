import importlib.util
from pathlib import Path

script = Path(__file__).resolve().parents[1] / 'scripts' / 'route_pdf_file.py'
spec = importlib.util.spec_from_file_location('report_map_router', script)
router = importlib.util.module_from_spec(spec)
spec.loader.exec_module(router)


def test_isolated_plan_does_not_make_fifty_page_scan_report_cad():
    sizes = [(595, 842)] * 49 + [(1191, 842)]
    kind, evidence = router.classify_document_kind(sizes, [0] * 50)
    assert kind == 'document'
    assert 'isolated_drawing_attachments' in evidence


def test_real_drawing_sets_keep_existing_routing():
    assert router.classify_document_kind([(1684, 1191)], [50])[0] == 'engineering-drawing'
    assert router.classify_document_kind([(1684, 1191)] * 10, [50] * 10)[0] == 'engineering-drawing'

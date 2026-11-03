import sys
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import extract_scan


@pytest.mark.parametrize('fail', [False, True])
@pytest.mark.parametrize('cpus', [16, 2])
def test_engine_initialization_limits_threads_and_restores_runtime(monkeypatch, fail, cpus):
    class Options:
        intra_op_num_threads = 0
        inter_op_num_threads = 0
        def add_session_config_entry(self, key, value):
            if not hasattr(self, 'entries'):
                self.entries = {}
            self.entries[key] = value
    runtime = SimpleNamespace(SessionOptions=Options)
    seen = []
    def create():
        seen.append(runtime.SessionOptions())
        if fail:
            raise RuntimeError('model failed')
        return object()
    monkeypatch.setitem(sys.modules, 'rapidocr_onnxruntime', SimpleNamespace(RapidOCR=create))
    monkeypatch.setitem(sys.modules, 'rapidocr_onnxruntime.utils', runtime)
    monkeypatch.setattr(os, 'cpu_count', lambda: cpus)
    if fail:
        with pytest.raises(RuntimeError, match='model failed'):
            extract_scan.create_ocr_engine()
    else:
        extract_scan.create_ocr_engine()
    assert seen[0].intra_op_num_threads == min(8, cpus)
    assert seen[0].inter_op_num_threads == 1
    assert seen[0].entries == {'session.intra_op.allow_spinning': '0', 'session.inter_op.allow_spinning': '0'}
    assert runtime.SessionOptions is Options

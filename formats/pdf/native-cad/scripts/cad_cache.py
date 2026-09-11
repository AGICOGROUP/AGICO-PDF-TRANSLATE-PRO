"""Page-local cache identity and lazy default OCR construction."""
from functools import lru_cache
import hashlib
from importlib import metadata, util
import json
from pathlib import Path

import pymupdf


def page_fingerprint(page):
    """Hash an isolated page including its resources, crop, rotation and annotations.

    Copying into a fresh PDF gives stable local object numbers and excludes the
    original document ID and unrelated pages. No rendering or OCR is necessary.
    Optional-content configuration and AcroForm state can affect rendering from
    outside the page's resource graph. These uncommon documents conservatively
    use the entire document plus page index instead of an isolated-page hash.
    """
    document = page.parent
    if any(document.xref_get_key(document.pdf_catalog(), key)[0] != 'null'
           for key in ('OCProperties', 'AcroForm')):
        content = document.tobytes(no_new_id=True)
        prefix = f'document-render-state-v1:{page.number}:'.encode()
        return hashlib.sha256(prefix + content).hexdigest()
    with pymupdf.open() as isolated:
        isolated.insert_pdf(document, from_page=page.number, to_page=page.number,
                            links=False, annots=True)
        content = isolated.tobytes(garbage=4, no_new_id=True)
    return hashlib.sha256(content).hexdigest()


@lru_cache(maxsize=128)
def _file_digest(path, size, mtime_ns, ctime_ns):
    # Stat values are part of the memoization key; model contents are hashed
    # once per file revision, rather than once per tile or page.
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _identity_file(path):
    path = Path(path).resolve()
    stat = path.stat()
    return _file_digest(str(path), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


def _model_files():
    spec = util.find_spec('rapidocr_onnxruntime')
    if spec is None or spec.origin is None:
        return []
    root = Path(spec.origin).parent
    # Includes default detector/classifier/recognizer models and dictionaries
    # or configuration consumed by the installed RapidOCR package.
    return sorted(path for path in root.rglob('*')
                  if path.is_file() and path.suffix.lower() in ('.onnx', '.yaml', '.yml', '.txt'))


def ocr_identity():
    """Fingerprint installed defaults without importing or initializing OCR."""
    dependencies = {}
    for name in ('rapidocr-onnxruntime', 'onnxruntime', 'numpy', 'Pillow', 'PyMuPDF', 'opencv-python'):
        try:
            dependencies[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            dependencies[name] = 'not-installed'
    identity = {'version': 2, 'dependencies': dependencies,
                'implementation': _identity_file(Path(__file__)),
                'models': [(str(path), _identity_file(path)) for path in _model_files()]}
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


class LazyOCR:
    """A shared callable that constructs RapidOCR only on an actual cache miss."""

    def __init__(self, factory=None):
        self._factory = factory
        self._engine = None

    def __call__(self, image):
        if self._engine is None:
            factory = self._factory
            if factory is None:
                from rapidocr_onnxruntime import RapidOCR
                factory = RapidOCR
            self._engine = factory()
        return self._engine(image)

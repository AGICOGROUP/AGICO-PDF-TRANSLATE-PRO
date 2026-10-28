"""Exclude non-painting OCR layers from PDF content routing (no OCR needed)."""
from copy import copy

from pypdf.generic import ContentStream, DictionaryObject, NameObject


def _trace_char_count(page):
    """Count painted Unicode glyphs, merging MuPDF's fill/stroke span pairs."""
    count = 0
    previous = None
    for span in page.get_texttrace():
        if span['type'] == 3:
            previous = None
            continue
        identity = (span['font'], span['size'], span['bbox'], span['chars'])
        if span['type'] == 1 and previous == (0, span['seqno'] - 1, identity):
            previous = None
            continue
        count += sum(not chr(character[0]).isspace() for character in span['chars'])
        previous = (span['type'], span['seqno'], identity)
    return count


def native_char_count(page, *, trace_page=None):
    """Count only painting text; an optional trace avoids full pypdf decoding.

    Always parse page/Form content with pypdf so optional MuPDF recovery cannot
    turn an unreadable content stream into a successful route.
    """
    decode_text = trace_page is None

    def count_stream(stream, resources, mode=0, active=frozenset()):
        if stream is None:
            return 0
        stream = stream.get_object()
        identity = id(stream)
        if identity in active:
            raise ValueError('cyclic Form XObject during text classification')
        active = active | {identity}
        stack = []
        operations = []
        visible = False
        form_count = 0
        resources = resources.get_object() if resources else DictionaryObject()
        for args, op in ContentStream(stream, page.pdf, 'bytes').operations:
            if op == b'q':
                stack.append(mode)
            elif op == b'Q':
                mode = stack.pop() if stack else 0
            elif op == b'Tr':
                mode = int(args[0])
            elif op in (b'Tj', b'TJ', b"'", b'"'):
                if mode in (3, 7):
                    continue
                values = args[0] if op == b'TJ' else [args[-1]]
                if any(isinstance(value, (str, bytes)) and value.strip() for value in values):
                    visible = True
            elif op == b'Do':
                xobjects = resources.get('/XObject', {})
                xobjects = xobjects.get_object() if xobjects else {}
                obj = xobjects.get(args[0])
                if obj is not None:
                    obj = obj.get_object()
                    if obj.get('/Subtype') == '/Form':
                        form_count += count_stream(
                            obj, obj.get('/Resources', resources), mode, active
                        )
                # Forms are decoded separately with their own resources and the
                # caller's render mode; pypdf otherwise includes their hidden text.
                continue
            if decode_text:
                operations.append((args, op))
        if not visible:
            return form_count
        if not decode_text:
            return form_count + 1
        content = ContentStream(None, page.pdf)
        content.operations = operations
        filtered = copy(page)
        filtered[NameObject('/Contents')] = content
        filtered[NameObject('/Resources')] = resources
        return form_count + len(''.join((filtered.extract_text() or '').split()))

    count = count_stream(page.get_contents(), page.get('/Resources', {}))
    if decode_text or count == 0:
        return count
    try:
        traced_count = _trace_char_count(trace_page)
        if traced_count > 0:
            return traced_count
    except Exception:
        pass  # An optional probe failure must not disable the pypdf route.
    # Some fonts cannot be decoded by the optional backend. Do not lose a
    # native page merely because its trace returned no Unicode glyphs.
    decode_text = True
    return count_stream(page.get_contents(), page.get('/Resources', {}))

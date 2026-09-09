"""Exclude non-painting OCR layers from PDF content routing (no OCR needed)."""
from pypdf.generic import ContentStream


def native_char_count(page):
    def paints_text(stream, resources, mode=0, active=frozenset()):
        if stream is None:
            return False
        stream = stream.get_object()
        identity = id(stream)
        if identity in active:
            raise ValueError('cyclic Form XObject during text classification')
        active = active | {identity}
        stack = []
        resources = resources.get_object() if resources else {}
        for args, op in ContentStream(stream, page.pdf).operations:
            if op == b'q':
                stack.append(mode)
            elif op == b'Q':
                mode = stack.pop() if stack else 0
            elif op == b'Tr':
                mode = int(args[0])
            elif op in (b'Tj', b'TJ', b"'", b'"') and mode not in (3, 7):
                values = args[0] if op == b'TJ' else [args[-1]]
                if any(isinstance(value, (str, bytes)) and value.strip() for value in values):
                    return True
            elif op == b'Do':
                xobjects = resources.get('/XObject', {})
                xobjects = xobjects.get_object() if xobjects else {}
                obj = xobjects.get(args[0])
                if obj is not None:
                    obj = obj.get_object()
                    if obj.get('/Subtype') == '/Form' and paints_text(
                        obj, obj.get('/Resources', resources), mode, active
                    ):
                        return True
        return False

    if not paints_text(page.get_contents(), page.get('/Resources', {})):
        return 0
    # Retain established text-density heuristics for pages with painting text.
    return len(''.join((page.extract_text() or '').split()))

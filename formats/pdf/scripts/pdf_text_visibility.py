"""Exclude non-painting OCR layers from PDF content routing (no OCR needed)."""
from copy import copy

from pypdf.generic import ContentStream, DictionaryObject, NameObject


def _covered_by_final_opaque_image(page, trace_page):
    """Conservatively identify a scan painted over the complete text layer."""
    try:
        log = trace_page.get_bboxlog()
        images = trace_page.get_image_info(xrefs=True)
        if not log or log[-1][0] != 'fill-image' or not images:
            return False
        image = images[-1]
        a,b,c,d,_,_ = image['transform']
        if not ((abs(b)<1e-6 and abs(c)<1e-6) or (abs(a)<1e-6 and abs(d)<1e-6)):
            return False
        bounds = trace_page.rect * trace_page.derotation_matrix
        rect = type(bounds)(image['bbox'])
        if not rect.contains(bounds):
            return False
        resources = page.get('/Resources', {}).get_object()
        state, stack, final_safe = (1., False, False, '/Normal'), [], False
        paint = {b'Tj',b'TJ',b"'",b'"',b'S',b's',b'f',b'F',b'f*',b'B',b'B*',b'b',b'b*',b'sh'}
        for args, op in ContentStream(page.get_contents(), page.pdf, 'bytes').operations:
            alpha, clipped, masked, blend = state
            if op == b'q':stack.append(state)
            elif op == b'Q':state=stack.pop() if stack else (1.,False,False,'/Normal')
            elif op in (b'W', b'W*'):state=(alpha,True,masked,blend)
            elif op == b'gs':
                gs = resources.get('/ExtGState', {}).get_object()[args[0]].get_object()
                state=(float(gs.get('/ca',alpha)),clipped,
                       gs.get('/SMask','/None')!='/None' if '/SMask' in gs else masked,
                       str(gs.get('/BM',blend)))
            elif op == b'Do':
                obj = resources.get('/XObject', {}).get_object()[args[0]].get_object()
                final_safe=(obj.get('/Subtype')=='/Image' and alpha==1. and not clipped
                    and not masked and blend in ('/Normal','/Compatible')
                    and not obj.get('/ImageMask') and '/SMask' not in obj and '/Mask' not in obj)
            elif op in paint:final_safe=False
        return final_safe
    except (AttributeError,KeyError,TypeError,ValueError,RuntimeError):
        return False


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
    if count and trace_page is not None and _covered_by_final_opaque_image(page, trace_page):
        return 0
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

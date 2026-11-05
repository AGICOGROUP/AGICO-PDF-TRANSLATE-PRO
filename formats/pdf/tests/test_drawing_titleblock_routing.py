import json
from pathlib import Path
import subprocess
import sys

import pytest
from reportlab.pdfgen import canvas

ROUTER = Path(__file__).resolve().parents[1] / 'scripts' / 'route_pdf_file.py'


def route_sheet(tmp_path, title, *, portrait=False, hidden=False):
    source = tmp_path / 'source.pdf'
    size = (612, 792) if portrait else (842, 595)
    pdf = canvas.Canvas(str(source), pagesize=size)
    for i in range(350):
        pdf.line(20 + i % 30 * 10, 40, 40 + i % 30 * 10, 420)
    for i in range(25):
        pdf.drawString(30, 450 - i * 12, f'{i} Value 123.45')
    if hidden:
        text = pdf.beginText(25, 20); text.setTextRenderMode(3)
        text.textLine(title); pdf.drawText(text)
    else:
        pdf.drawString(25, 20, title)
    pdf.save()
    result = subprocess.run([sys.executable, str(ROUTER), str(source), '--mode', 'replace'],
                            capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize('title,portrait', [
    ('SECTION A-A   DRG.No. QX-27   SCALE 1:15', False),
    ('SURFACE FINISH    NOS.REQD.    DRG.No. AB-12', False),
    ('Contract No.CMEC2006C4094    DATE    1:15    SCALE', True),
])
def test_dense_small_sheet_with_visible_drawing_titleblock(tmp_path, title, portrait):
    result = route_sheet(tmp_path, title, portrait=portrait)
    assert result['document_kind'] == 'engineering-drawing'
    assert result['adapter'] == 'formats/pdf/native-cad/SKILL.md'


@pytest.mark.parametrize('title,hidden', [
    ('NUMERIC RESULTS TABLE', False),
    ('SCALE 1:15', False),
    ('SECTION A-A DRG.No. QX-27 SCALE 1:15', True),
])
def test_dense_table_or_hidden_titleblock_stays_document(tmp_path, title, hidden):
    assert route_sheet(tmp_path, title, hidden=hidden)['document_kind'] == 'document'

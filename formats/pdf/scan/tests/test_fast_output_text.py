import importlib.util
import sys
from pathlib import Path
import pytest
from reportlab.pdfgen import canvas
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import verify_scan as v

def fixture_pdf(tmp_path, overlap=False, rotation=0):
    p=tmp_path/'actual.pdf'; c=canvas.Canvas(str(p),pagesize=(300,300))
    c.saveState();c.translate(150,150);c.rotate(-rotation);c.drawString(0,0,'Actual 35 degrees');c.restoreState()
    if overlap:c.drawString(150,150,'Second overlap')
    c.save()
    m={'pages':[{'source_page':1,'width_pt':300,'height_pt':300,'pixel_width':300,'pixel_height':300}], 'blocks':[{'id':'a','page':1,'status':'translated','action':'replace','translation':'Actual 35 degrees','box':[50,50,250,250],'rotation':rotation}]}
    return p,m

@pytest.mark.parametrize('rotation',[0,90,180,270])
def test_actual_pdf_fast_direction_and_immutable(tmp_path,rotation,monkeypatch):
    p,m=fixture_pdf(tmp_path,rotation=rotation);before=p.read_bytes()
    monkeypatch.setattr(v,'_extract_output_text_legacy',lambda *a,**k:pytest.fail('unexpected fallback'))
    ori=[]; physical={};text,overlap=v.extract_output_text(p,[1],manifest=m,orientation_failures=ori,extracted_by_output=physical)
    assert v._translation_present(m['blocks'][0],text[1]);assert not ori and not overlap;assert physical==text;assert p.read_bytes()==before

@pytest.mark.parametrize('reason',['overlap','missing','direction','absent','glyph'])
def test_suspicion_falls_back_without_partial_results(tmp_path,monkeypatch,reason):
    p,m=fixture_pdf(tmp_path,overlap=reason=='overlap')
    if reason=='missing':m['blocks'][0]['translation']='Absent actual content'
    if reason=='direction':m['blocks'][0]['rotation']=180
    if reason=='absent':monkeypatch.setitem(sys.modules,'pymupdf',None)
    if reason=='glyph':
        import pymupdf
        original=pymupdf.Page.get_text
        def invalid_char(page, option='text', *args, **kwargs):
            result=original(page, option, *args, **kwargs)
            if option=='rawdict':result['blocks'][0]['lines'][0]['spans'][0]['chars'][0]['c']='\ufffd'
            return result
        monkeypatch.setattr(pymupdf.Page,'get_text',invalid_char)
    calls=[]
    def legacy(*args,**kwargs):
        calls.append(True);assert kwargs['orientation_failures']==[];assert kwargs['extracted_by_output']=={};return {1:'legacy evidence'},[]
    monkeypatch.setattr(v,'_extract_output_text_legacy',legacy)
    assert v.extract_output_text(p,[1],manifest=m,orientation_failures=[],extracted_by_output={})[0]=={1:'legacy evidence'};assert calls

def test_unicode_actual_pdf(tmp_path,monkeypatch):
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    font=Path('C:/Windows/Fonts/arial.ttf')
    if not font.exists():pytest.skip('fixture font unavailable')
    pdfmetrics.registerFont(TTFont('actualUnicode',str(font)))
    p=tmp_path/'unicode.pdf';c=canvas.Canvas(str(p));c.setFont('actualUnicode',12);c.drawString(30,700,'35°C ±2 Ω ≤ 20 ≥ 10');c.save()
    monkeypatch.setattr(v,'_extract_output_text_legacy',lambda *a,**k:pytest.fail('unexpected fallback'))
    text,_=v.extract_output_text(p,[1]);assert all(x in text[1] for x in ['35°C','±2','Ω','≤','≥'])


def test_real_legacy_overlap_and_wrong_direction_are_not_dismissed(tmp_path):
    p,m=fixture_pdf(tmp_path,overlap=True)
    _, overlaps=v.extract_output_text(p,[1],manifest=m)
    assert overlaps
    p,m=fixture_pdf(tmp_path,rotation=90);m['blocks'][0]['rotation']=270
    failures=[];v.extract_output_text(p,[1],manifest=m,orientation_failures=failures)
    assert failures[0]['actual_rotations']==[90]

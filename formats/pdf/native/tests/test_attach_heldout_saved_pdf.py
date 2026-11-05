"""Held-out current-run saved-PDF invariants, independent of attachment examples."""
import importlib.util
import io
import sys
from pathlib import Path
import pymupdf
from pypdf import PdfReader
from pypdf.generic import ArrayObject, FloatObject, NameObject
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from PIL import Image, ImageDraw
ROOT=Path(__file__).resolve().parents[1]/'scripts'
def load(name,file):
 spec=importlib.util.spec_from_file_location(name,ROOT/file);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
r=load('heldout_native_rebuild','native_selectable_rebuild.py')
p=load('heldout_native_pipeline','pdf_translation_pipeline.py')
def test_saved_nonstandard_page_geometry_and_rotation(tmp_path):
 source=tmp_path/'source.pdf';pdf=canvas.Canvas(str(source),pagesize=(612.25,792.125));pdf.drawString(40,650,'Fresh independently authored mechanical fixture');pdf.save()
 reader=PdfReader(source);page=reader.pages[0];page[NameObject('/CropBox')]=ArrayObject([FloatObject(v) for v in (3.125,4.25,609.75,788.875)]);page.rotate(180)
 from pypdf import PdfWriter
 writer=PdfWriter();writer.add_page(page);writer.write(source)
 writer,_=r.strip_native_text(source);target=tmp_path/'rewritten.pdf';writer.write(target)
 before=PdfReader(source).pages[0];after=PdfReader(target).pages[0]
 for key in ('/MediaBox','/CropBox'):assert tuple(before[key])==tuple(after[key])
 assert after.rotation==before.rotation==180
 with pymupdf.open(target) as doc:assert doc[0].get_pixmap().width>0

def test_final_unicode_font_agrees_with_fitting_and_saved_glyphs(tmp_path):
 r.register_fonts();text='✓ Ω № 27 — 已完成';style=r.rendered_font_style({'size':12,'bold':False},text)
 face=pdfmetrics.getFont(r.font_key(style)).face
 assert all(face.charToGlyph.get(ord(c),0) for c in text if not c.isspace())
 assert Path(p.font_file(style)).name.casefold()==Path(face.filename).name.casefold()
 output=tmp_path/'unicode.pdf';pdf=canvas.Canvas(str(output),pagesize=(612.25,792.125));pdf.setFont(r.font_key(style),12);pdf.drawString(30,700,text);pdf.save()
 with pymupdf.open(output) as doc:
  assert text in doc[0].get_text()
  assert doc[0].get_pixmap().width>0

def test_four_bold_character_prefix_body_vs_heading_and_footer():
 def block(text,y,height,runs,bold=False):return {'id':str(y),'source_text':text,'bbox':[40,y,570,y+height],'runs':runs,'style':{'font':'Arial-Bold' if bold else 'Arial','size':12,'bold':bold},'lines':[]}
 body=block('NOTE Operation remains conditional on verified feed properties and continuous measurements. '*4,650,113,[{'text':'NOTE','bold':True},{'text':' Operation remains conditional on verified feed properties and continuous measurements. '*4,'bold':False}])
 heading=block('Acceptance conditions',120,16,[],True)
 footer=block('Issue 4 | 2026-11-03',806,14,[])
 baseline=block('Standard body paragraph.',300,14,[])
 p.classify_document_roles([{'height':842,'table_cells':[],'blocks':[body,heading,footer,baseline]}])
 assert body['role'].startswith('body-') and not body['style']['source_bold']
 assert heading['role'].startswith('heading-')
 assert footer['role']=='footer'

def test_ordinary_headings_keep_bold_and_unsupported_glyph_fails_closed():
 import pytest
 r.register_fonts()
 style=r.rendered_font_style({'bold':True,'size':12},'Acceptance Conditions')
 assert r.font_key(style)=='ArialV5-Bold'
 with pytest.raises(ValueError,match='No installed render font covers'):
  r.rendered_font_style({'size':12},'Missing \U0010ffff')


def test_ordinary_font_registration_is_lazy_but_missing_glyph_loads_fallback():
 import subprocess
 script = r"""
import importlib.util, sys
from pathlib import Path
from reportlab.pdfbase import pdfmetrics
root=Path(sys.argv[1])
def load(name,file):
 spec=importlib.util.spec_from_file_location(name,root/file);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
r=load('lazy_rebuild','native_selectable_rebuild.py');p=load('lazy_pipeline','pdf_translation_pipeline.py')
fonts=r.register_fonts()
assert 'ArialUnicodeV5' not in fonts
assert 'ArialUnicodeV5' not in pdfmetrics.getRegisteredFontNames()
assert r.font_key(r.rendered_font_style({'size':12},'Ordinary operating conditions'))=='ArialV5'
assert 'ArialUnicodeV5' not in pdfmetrics.getRegisteredFontNames()
style=r.rendered_font_style({'size':12},'✓ 完成')
assert style['unicode_fallback']
assert 'ArialUnicodeV5' in pdfmetrics.getRegisteredFontNames()
assert Path(p.font_file(style)).name.casefold()==Path(pdfmetrics.getFont(r.font_key(style)).face.filename).name.casefold()
"""
 result=subprocess.run([sys.executable,'-X','utf8','-c',script,str(ROOT)],capture_output=True,text=True)
 assert result.returncode==0,result.stderr

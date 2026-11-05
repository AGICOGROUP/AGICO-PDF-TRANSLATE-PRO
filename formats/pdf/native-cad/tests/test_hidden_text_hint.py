import pymupdf
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from native_cad_pipeline import extract_records

def test_hidden_text_is_only_located_hint_not_editable_visible_ink():
    doc=pymupdf.open();page=doc.new_page()
    page.insert_text((40,50),'Visible title')
    page.insert_text((40,90),'Hidden source label',render_mode=3)
    before=doc.tobytes(no_new_id=True)
    records=extract_records(doc)
    visible=next(r for r in records if r['source']=='Visible title')
    hidden=next(r for r in records if r['source']=='Hidden source label')
    assert visible.get('kind','native')=='native'
    assert hidden.get('kind')=='outline'
    assert hidden['reading_method']=='hidden_text_hint_requires_source_review'
    assert doc.tobytes(no_new_id=True)==before

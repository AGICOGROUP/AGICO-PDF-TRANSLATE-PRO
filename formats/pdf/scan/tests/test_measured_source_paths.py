import copy
import hashlib
import sys
from pathlib import Path

import numpy as np
import pymupdf
import pytest
from PIL import Image, ImageDraw
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import build_scan
from contracts import ManifestError, validate_source_paths


def block():
    return {'action':'replace', 'clean_box':[5,5,65,65], 'background':[255,255,255],
            'protected_source_paths':[{'points':[[10,10],[60,60]], 'width':1,
                'review_note':'Measured exact source line, clear label outside narrow mask.'}]}


@pytest.mark.parametrize('width', [0,-1,4,float('nan'),float('inf'),True,'1',None])
def test_invalid_width_is_rejected(width):
    row=block();row['protected_source_paths'][0]['width']=width
    with pytest.raises(ManifestError):validate_source_paths(row,80,80)


@pytest.mark.parametrize('field,value', [('review_note',True),('review_note',''),
    ('points',[[1,float('nan')],[2,2]]),('points',[[-1,1],[2,2]]),
    ('points',[[True,1],[2,2]]),('points',[[1,1]])])
def test_invalid_geometry_or_note_is_rejected(field,value):
    row=block();row['protected_source_paths'][0][field]=value
    with pytest.raises(ManifestError):validate_source_paths(row,80,80)


def test_owner_collision_rejected_instead_of_restoring_other_source_text():
    source=Image.new('RGB',(80,80),'white')
    with pytest.raises(ValueError,match='another replacement owner'):
        build_scan.clean_background(source,[block(),{'action':'replace','clean_box':[20,20,50,50]}])


def test_missing_canvas_rejected():
    with pytest.raises(ManifestError):validate_source_paths(block(),None,80)


def test_compiler_copies_paths_without_aliasing_decisions(tmp_path):
    from compile_translation import compile_translation
    raster=tmp_path/'render.png';Image.new('RGB',(80,80),'white').save(raster)
    extraction={'source':'source.pdf','source_sha256':'a'*64,'selected_pages':[1],
        'pages':[{'source_page':1,'pixel_width':80,'pixel_height':80,'width_pt':80,
                  'height_pt':80,'render_path':str(raster)}],
        'source_lines':[{'id':'one','page':1,'text':'Source','box':[5,5,65,65],'rotation':0}]}
    paths=block()['protected_source_paths']
    decisions={'source_sha256':'a'*64,'target_language':'en','regions':[
        {'id':'one','ids':['one'],'translation':'Target','protected_source_paths':paths}]}
    compiled=compile_translation(extraction,{'source_sha256':'a'*64,'groups':[]},decisions)
    assert compiled['blocks'][0]['protected_source_paths']==paths
    paths[0]['points'][0][0]=11
    assert compiled['blocks'][0]['protected_source_paths'][0]['points'][0][0]==10


def test_source_path_changes_invalidate_clean_cache(tmp_path):
    source=Image.new('RGB',(80,80),'white');ImageDraw.Draw(source).line((10,10,60,60),fill='black')
    raster=tmp_path/'source.png';source.save(raster)
    page={'source_page':1,'pixel_width':80,'pixel_height':80,'render_path':str(raster)}
    row=block()
    first,_,_,hit=build_scan.prepare_clean_base(page,[row],tmp_path/'cache');assert not hit
    _,_,_,hit=build_scan.prepare_clean_base(page,[row],tmp_path/'cache');assert hit
    row['protected_source_paths'][0]['points']=[[10,11],[60,61]]
    changed,_,_,hit=build_scan.prepare_clean_base(page,[row],tmp_path/'cache');assert not hit
    assert first.getpixel((30,30))==(0,0,0)
    assert changed.getpixel((30,30))==(255,255,255)


def test_saved_pdf_preserves_actual_curve_and_signature_with_selectable_target(tmp_path):
    source=Image.new('RGB',(320,220),'white');draw=ImageDraw.Draw(source)
    points=[(40,40),(45,43),(50,48),(55,55),(60,64),(65,75)]
    draw.line(points,fill='black');draw.text((42,63),'TEXT',fill='black')
    draw.text((140,50),'CAPTION',fill='black')
    draw.line([(135,42),(149,67),(166,43),(184,69)],fill=(20,60,210),width=2)
    raster=tmp_path/'source.png';source.save(raster)
    pdf=tmp_path/'source.pdf';c=canvas.Canvas(str(pdf),pagesize=source.size,invariant=1)
    c.drawImage(ImageReader(source),0,0,width=320,height=220);c.save()
    before=pdf.read_bytes()
    page={'source_page':1,'width_pt':320,'height_pt':220,'pixel_width':320,
          'pixel_height':220,'render_path':str(raster),'dpi':72}
    lines=[{'id':'curve','page':1,'text':'TEXT','box':[38,38,70,80],'rotation':0},
           {'id':'caption','page':1,'text':'CAPTION','box':[130,38,195,75],'rotation':0}]
    blocks=[{'id':line['id'],'page':1,'source_line_ids':[line['id']], 'source':line['text'],
        'translation':'Translated','role':'body','status':'translated','action':'replace',
        'box':[20,120+i*35,260,150+i*35],'clean_box':line['box'], 'background':[255,255,255],
        'rotation':0} for i,line in enumerate(lines)]
    blocks[0]['protected_source_paths']=[{'points':points,'width':1,'review_note':'Exact measured source curve'}]
    blocks[1]['preserve_colored_ink']=True
    manifest={'source':str(pdf),'source_sha256':hashlib.sha256(before).hexdigest(),
        'target_language':'en','selected_pages':[1],'pages':[page],'source_lines':lines,'blocks':blocks}
    output=tmp_path/'target.pdf';report=build_scan.build_pdf(manifest,output,use_page_cache=False)
    assert pdf.read_bytes()==before
    assert report['pages'][0]['background_encoding']=='original_pdf_with_local_patches'
    assert report['outside_approved_pixel_changes']==0
    with pymupdf.open(output) as saved:
        assert saved[0].get_text().count('Translated')==2
        pix=saved[0].get_pixmap(alpha=False)
        target=np.asarray(Image.frombytes('RGB',(pix.width,pix.height),pix.samples))
    original=np.asarray(source)
    mask=Image.new('1',source.size);ImageDraw.Draw(mask).line(points,fill=1)
    assert np.array_equal(original[np.asarray(mask)],target[np.asarray(mask)])
    blue=original[:,:,2]-original[:,:,0].astype(int)>100
    assert np.array_equal(original[blue],target[blue])
    assert tuple(target[66,45])==(255,255,255)  # source label cleaned, not restored
    mismatched=copy.deepcopy(page);mismatched['pixel_width']=321
    with pytest.raises(ValueError,match='pixel canvas'):
        build_scan.prepare_clean_base(mismatched,blocks,tmp_path/'bad-clean')

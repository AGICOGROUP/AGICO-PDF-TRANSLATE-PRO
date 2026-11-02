import sys
from pathlib import Path
import pymupdf
import pytest
from PIL import Image, ImageDraw
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import native_cad_pipeline as pipeline


def test_raster_review_binds_pixels_box_and_colored_background(tmp_path):
    image=Image.new('RGB',(400,200),(225,240,205));ImageDraw.Draw(image).text((30,30),'Soil',fill='black')
    path=tmp_path/'source.png';image.save(path)
    doc=pymupdf.open();page=doc.new_page(width=400,height=200);page.insert_image(page.rect,filename=str(path))
    proof=pipeline.raster_cover_evidence(page,[[20,20,100,60]])
    assert proof[0]['background_rgb']==pytest.approx([225/255,240/255,205/255],abs=.01)
    assert proof==pipeline.raster_cover_evidence(page,[[20,20,100,60]])
    assert proof!=pipeline.raster_cover_evidence(page,[[20,20,110,60]])
    page.draw_rect(pymupdf.Rect(25,25,40,40),fill=(1,0,0),overlay=True)
    assert proof!=pipeline.raster_cover_evidence(page,[[20,20,100,60]])
    with pytest.raises(ValueError):pipeline.raster_cover_evidence(page,[[-1,0,10,10]])


def test_grey_header_supported_but_dark_photo_field_rejected(tmp_path):
    for color, allowed in [((168,176,160),True),((30,40,45),False)]:
        image=Image.new('RGB',(100,60),color);path=tmp_path/'field.png';image.save(path)
        doc=pymupdf.open();page=doc.new_page(width=100,height=60);page.insert_image(page.rect,filename=str(path))
        if allowed:
            assert pipeline.raster_cover_evidence(page,[[10,10,90,50]])[0]['background_rgb']==pytest.approx([v/255 for v in color],abs=.01)
        else:
            with pytest.raises(ValueError):pipeline.raster_cover_evidence(page,[[10,10,90,50]])

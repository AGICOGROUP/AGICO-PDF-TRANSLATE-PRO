import sys
from pathlib import Path
import pytest
from PIL import Image, ImageDraw
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_scan import apply_prose_frame_reflows

def sample():
    im = Image.new('RGB', (100, 140), 'white')
    d = ImageDraw.Draw(im)
    d.rectangle((10,10,89,59), outline='black')
    d.rectangle((11,11,88,19), fill=(180,200,130))
    return im

def item():
    return {'kind':'prose_callout', 'reason':'Complete translation at 9pt needs available blank space.',
            'original_box':[10,10,90,60], 'target_box':[10,70,90,130], 'header_height':10, 'border_width':1}

def test_frame_keeps_header_and_border_pixels_without_stretching():
    im=sample(); out, report=apply_prose_frame_reflows(im, {'prose_frame_reflows':[item()]})
    assert out.crop((10,70,90,80)).tobytes()==im.crop((10,10,90,20)).tobytes()
    assert out.crop((10,129,90,130)).tobytes()==im.crop((10,59,90,60)).tobytes()
    assert out.getpixel((10,110))==(0,0,0)
    assert out.getpixel((50,110))==(255,255,255)
    assert out.getpixel((10,10))==(255,255,255)
    assert report['prose_frame_reflow_count']==1

def test_frame_rejects_uncleared_or_graphic_interior():
    im=sample(); ImageDraw.Draw(im).rectangle((40,30,45,35),fill='black')
    with pytest.raises(ValueError,match='interior'):
        apply_prose_frame_reflows(im,{'prose_frame_reflows':[item()]})

def test_frame_rejects_nonblank_destination():
    im=sample(); im.putpixel((50,100),(255,0,0))
    with pytest.raises(ValueError,match='destination'):
        apply_prose_frame_reflows(im,{'prose_frame_reflows':[item()]})

def test_frame_rejects_engineering_table_or_width_change():
    for change in ({'kind':'engineering_table'},{'target_box':[10,70,91,130]}):
        spec=item();spec.update(change)
        with pytest.raises(ValueError):apply_prose_frame_reflows(sample(),{'prose_frame_reflows':[spec]})

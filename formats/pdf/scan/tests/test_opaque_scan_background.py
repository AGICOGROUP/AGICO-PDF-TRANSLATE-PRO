import hashlib
import sys
from pathlib import Path
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import build_scan

def test_occluded_native_layer_keeps_encoded_scan_background(tmp_path):
    source=tmp_path/'source.pdf';pdf=canvas.Canvas(str(source),pagesize=(240,300))
    pdf.drawString(20,150,'Hidden original text')
    pdf.drawImage(ImageReader(Image.new('RGB',(240,300),'white')),0,0,240,300)
    pdf.save();before=source.read_bytes()
    manifest={'source':str(source),'source_sha256':hashlib.sha256(before).hexdigest(),
              'pages':[{'source_page':1,'width_pt':240,'height_pt':300}]}
    _,bases=build_scan._source_backgrounds(manifest)
    assert 1 in bases
    assert source.read_bytes()==before

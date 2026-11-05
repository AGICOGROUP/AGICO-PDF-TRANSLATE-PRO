import json
from pathlib import Path
import subprocess
import sys
import pytest
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

ROUTER=Path(__file__).resolve().parents[1]/'scripts/route_pdf_file.py'

@pytest.mark.parametrize('mode,want', [('opaque','scan-only'),('many','scan-only'),('before','native-text'),
    ('alpha','native-text'),('partial','native-text'),('clipped','native-text'),
    ('masked','native-text'),('skew','native-text')])
def test_only_final_unmasked_opaque_whole_page_image_hides_native(tmp_path,mode,want):
    p=tmp_path/'source.pdf';pdf=canvas.Canvas(str(p),pagesize=(240,300))
    image=Image.new('RGB',(24,30),'white')
    def picture():
        pdf.saveState()
        if mode=='alpha':pdf.setFillAlpha(.5)
        if mode=='clipped':
            path=pdf.beginPath();path.rect(0,0,120,300);pdf.clipPath(path,stroke=0)
        if mode=='skew':pdf.transform(1,.5,.5,1,-75,-60)
        if mode=='masked':
            rgba=image.convert('RGBA');rgba.putalpha(128)
            pdf.drawImage(ImageReader(rgba),0,0,240,300,mask='auto')
        else:pdf.drawImage(ImageReader(image),0,0,120 if mode=='partial' else 240,300)
        pdf.restoreState()
    if mode=='before':picture()
    pdf.drawString(20,150,'Text behind the scan image')
    if mode=='many':
        for i in range(5):pdf.drawString(20,135-i*12,'Another span in the same block')
    if mode!='before':picture()
    pdf.save()
    result=subprocess.run([sys.executable,str(ROUTER),str(p),'--mode','replace'],capture_output=True,text=True,encoding='utf-8')
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)['pdf_type']==want

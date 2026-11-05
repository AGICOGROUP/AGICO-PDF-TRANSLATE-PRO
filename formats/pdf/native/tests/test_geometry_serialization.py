import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path
from pypdf import PdfReader

spec=importlib.util.spec_from_file_location('native_geometry_rebuild',Path(__file__).resolve().parents[1]/'scripts/native_selectable_rebuild.py')
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)

def source_pdf():
 objects=[b'<< /Type /Catalog /Pages 2 0 R >>',
          b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
          b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595.2755905511812 841.8897637795277] /CropBox [0.123456789 0.234567891 595.2755905511812 841.8897637795277] /Rotate 90 /Resources << >> >>']
 data=b'%PDF-1.7\n'; offsets=[0]
 for n,obj in enumerate(objects,1):
  offsets.append(len(data));data+=f'{n} 0 obj\n'.encode()+obj+b'\nendobj\n'
 at=len(data);data+=b'xref\n0 4\n0000000000 65535 f \n'
 data+=b''.join(f'{off:010d} 00000 n \n'.encode() for off in offsets[1:])
 return data+f'trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n{at}\n%%EOF\n'.encode()

class GeometrySerializationTests(unittest.TestCase):
 def test_native_rewrite_preserves_exact_source_boxes_and_rotation(self):
  data=source_pdf();original=PdfReader(io.BytesIO(data)).pages[0]
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory)/'source.pdf';path.write_bytes(data)
   writer,_=module.strip_native_text(path)
   stream=io.BytesIO();writer.write(stream);actual=PdfReader(stream).pages[0]
  for key in ('/MediaBox','/CropBox'):
   self.assertEqual(tuple(map(float,original[key])),tuple(map(float,actual[key])))
  self.assertEqual(original['/Rotate'],actual['/Rotate'])

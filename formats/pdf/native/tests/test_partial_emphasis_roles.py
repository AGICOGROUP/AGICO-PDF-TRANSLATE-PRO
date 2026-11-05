import importlib.util
import sys
import unittest
from pathlib import Path

spec=importlib.util.spec_from_file_location('native_emphasis_roles',Path(__file__).resolve().parents[1]/'scripts/pdf_translation_pipeline.py')
pipeline=importlib.util.module_from_spec(spec);sys.modules[spec.name]=pipeline;spec.loader.exec_module(pipeline)

def block(text,bold=False,runs=None,height=16):
 return {'id':'sample','source_text':text,'bbox':[50,120,545,120+height],
         'style':{'font':'Calibri-Bold' if bold else 'Calibri','size':12,'bold':bold},
         'runs':runs or [],'lines':[{'text':text,'bbox':[50,120,545,120+height]}]}

def classify(item):
 baseline=block('Regular body reading text establishes the source body font.');baseline['bbox']=[50,300,545,316]
 pipeline.classify_document_roles([{'height':842,'table_cells':[],'blocks':[item,baseline]}])
 return item

class PartialEmphasisRoleTests(unittest.TestCase):
 def test_low_body_paragraph_and_continuation_are_not_footer(self):
  for box in ([50,656.5,545,776.136],[50,705.22,545,778.776],[50,779.496,545,791.496]):
   item=block('This is body copy, continuing the operating and feedstock basis.')
   item['bbox']=box
   with self.subTest(box=box):self.assertTrue(classify(item)['role'].startswith('body-'))
  footer=block('Issue date: 12 October 2026 | Tender basis for bids')
  footer['bbox']=[50,806.85,545,816.81];footer['style']['size']=9.96
  self.assertEqual('footer',classify(footer)['role'])

 def test_body_with_bold_numeric_prefix_and_inline_label_is_not_heading(self):
  runs=[{'text':'10.0 t/day','font':'Calibri-Bold','bold':True},
        {'text':' of finished product at the packaging point. Final guarantees remain conditional. '*8,'font':'Calibri','bold':False},
        {'text':'Base Configuration','font':'Calibri-Bold','bold':True}]
  item=classify(block(''.join(r['text']for r in runs),runs=runs,height=125))
  self.assertTrue(item['role'].startswith('body-'))
  self.assertFalse(item['style']['source_bold'])
  self.assertEqual(12,item['style']['role_size'])
  self.assertEqual(runs,item['runs'],'Source inline emphasis evidence must remain intact')

 def test_long_fully_bold_paragraph_keeps_weight_without_becoming_heading(self):
  item=classify(block('A long emphasized body paragraph with contractual conditions. '*8,bold=True,height=96))
  self.assertTrue(item['role'].startswith('body-'))
  self.assertTrue(item['style']['bold'])

 def test_bold_bullet_is_body_but_actual_short_bold_heading_stays_heading(self):
  bullet=classify(block('• Output: 10.0 t/day at the packaging point.',bold=True))
  self.assertTrue(bullet['role'].startswith('body-'))
  heading=classify(block('Process and Performance Guarantees',bold=True))
  self.assertTrue(heading['role'].startswith('heading-'))

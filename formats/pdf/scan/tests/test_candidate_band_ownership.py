import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from contracts import unresolved_scan_candidates

@pytest.mark.parametrize('recovered',[False,True])
def test_separate_located_fields_can_cover_one_candidate_band(recovered):
    m={'selected_pages':[1],'pages':[{'source_page':1,'ocr_review_candidates':[{'id':'c','box':[0,0,100,10]}]}],
       'source_lines':[{'id':'a','page':1,'box':[0,0,45,10]},{'id':'b','page':1,'box':[55,0,100,10]}]}
    if recovered:m['candidate_dispositions']={'c':{'disposition':'recovered','source_line_ids':['a','b']}}
    assert unresolved_scan_candidates(m)==[]

def test_overlapping_boxes_cannot_inflate_source_coverage():
    m={'selected_pages':[1],'pages':[{'source_page':1,'ocr_review_candidates':[{'id':'c','box':[0,0,100,10]}]}],
       'source_lines':[{'id':str(i),'page':1,'box':[0,0,45,10]} for i in range(10)]}
    assert unresolved_scan_candidates(m)==['c']

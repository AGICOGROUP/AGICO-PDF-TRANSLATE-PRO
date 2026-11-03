"""Anonymous synthetic controls from the measured native workflow, not user data."""
import argparse
import importlib.util
import json
import sys
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[4]
spec=importlib.util.spec_from_file_location('payload_native_pipeline',ROOT/'formats/pdf/native/scripts/pdf_translation_pipeline.py')
pipeline=importlib.util.module_from_spec(spec);sys.modules[spec.name]=pipeline;spec.loader.exec_module(pipeline)

ZH='开机前应检查润滑油液位及冷却水压力。只有防护罩全部安装并确认联锁有效后，才允许启动设备。空载连续试运行30 min；如出现异常振动、泄漏或温升超过35 ℃，应立即停机并记录原因。未经检查确认，不得重新启动。表中功率为单机额定值，数量不表示同时运行的设备台数。'
EN='Before inspection, isolate the electrical supply and verify that the discharge valve is closed. Start the pump only after the guard is secured and the cooling circuit has been vented. Run the acceptance test for 45 min without interruption. If outlet pressure falls below 0.35 MPa or visible leakage occurs, stop the pump immediately. Record the actual installation elevation; the value in the table is a design reference and must not replace the site measurement.'

@pytest.mark.parametrize('language,paragraph', [('zh',ZH),('en',EN)])
def test_control_packet_has_single_source_ownership_and_bounded_payload(tmp_path,language,paragraph):
    if language=='zh':
        strings=['SYNTHETIC CONTROL / NOT A USER GOLDEN DOCUMENT','匿名设备试运行技术说明',paragraph,
                 '项目','数值','单位','设备型号','GTM-42','—','设备数量','2','台',
                 '单机额定功率','18.5','kW','安装标高','+12.350','m',
                 '空载试运行时间','30','min','冷却水压力','0.20–0.35','MPa','1 / 1']
    else:
        strings=['SYNTHETIC CONTROL / NOT A USER GOLDEN DOCUMENT','Anonymous auxiliary pump acceptance note',paragraph,
                 'Item','Value','Unit','Pump model','AP-17','—','Installed quantity','3','units',
                 'Motor rated power','7.5','kW','Pipe centre elevation','+6.800','m',
                 'Acceptance test duration','45','min','Outlet pressure range','0.35–0.50','MPa','1 / 1']
    manifest={'source_sha256':'synthetic-control','source_language':language,'target_language':'en' if language=='zh' else 'zh',
              'pages':[{'page':1,'blocks':[{'id':f'b{i}','source_text':text,'translation':'','role':'body'} for i,text in enumerate(strings)]}]}
    path=tmp_path/'manifest.json';path.write_text(json.dumps(manifest,ensure_ascii=False),encoding='utf-8');out=tmp_path/'packet.json'
    pipeline.export_translation_command(argparse.Namespace(manifest=str(path),output=str(out)))
    raw=out.read_text(encoding='utf-8');packet=json.loads(raw)
    assert len(raw.encode('utf-8'))<9000
    legacy_records=[]
    for i,record in enumerate(packet['records']):
        legacy_records.append({k:v for k,v in record.items() if not k.startswith('context_')})
        legacy_records[-1].update(context_before=strings[i-1] if i else '',context_after=strings[i+1] if i+1<len(strings) else '')
    legacy={'source_sha256':manifest['source_sha256'],'records':legacy_records}
    assert len(raw.encode('utf-8'))<=len((json.dumps(legacy,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
    assert all(not any(k.startswith('context_') for k in record) for record in packet['records'])
    assert raw.count(paragraph)==1
    assert [(r['id'],r['source_text']) for r in packet['records']]==[(b['id'],b['source_text']) for b in manifest['pages'][0]['blocks']]
    by_id={r['id']:r for r in packet['records']}
    assert [by_id[i]['source_text'] for i in packet['pages'][0]['ordered_source_ids']]==strings
    terms=packet['pages'][0]['terminology']
    assert not {'重','高','放电','管网漏失水量'} & {t['source'] for t in terms}
    assert all('line' not in t and '未经逐条专业校核' not in t.get('context','') for t in terms)

def test_compact_packet_and_legacy_context_packet_both_keep_import_validation(tmp_path):
    manifest={'source_sha256':'fixed','source_language':'zh','target_language':'en','pages':[{'page':1,'blocks':[
        {'id':'b1','source_text':'额定功率10 kW','translation':'','protected_tokens':['10 kW']}]}]}
    path=tmp_path/'manifest.json';out=tmp_path/'packet.json'
    for legacy in (False,True):
        path.write_text(json.dumps(manifest),encoding='utf-8')
        pipeline.export_translation_command(argparse.Namespace(manifest=str(path),output=str(out)))
        packet=json.loads(out.read_text(encoding='utf-8'));packet['records'][0]['translation']='Rated power10 kW'
        assert packet['records'][0]['protected_tokens']==['10 kW']
        if legacy:
            packet['pages'][0]['page_context']='额定功率10 kW'
            packet['records'][0].update(context_before='',context_after='')
        out.write_text(json.dumps(packet),encoding='utf-8')
        pipeline.merge_translation_command(argparse.Namespace(manifest=str(path),packet=str(out),allow_cjk=False))
        assert json.loads(path.read_text(encoding='utf-8'))['pages'][0]['blocks'][0]['translation']=='Rated power10 kW'
        assert json.loads(path.read_text(encoding='utf-8'))['pages'][0]['blocks'][0]['protected_tokens']==['10 kW']

@pytest.mark.parametrize('change', ['source_sha256','source_language','target_language','source_text','duplicate'])
def test_compact_and_legacy_packets_cannot_bypass_bound_import_checks(tmp_path,change):
    for legacy in (False,True):
        manifest={'source_sha256':'fixed','source_language':'zh','target_language':'en','pages':[{'page':1,'blocks':[
            {'id':'b1','source_text':'额定功率10 kW','translation':''}]}]}
        path=tmp_path/'manifest.json';path.write_text(json.dumps(manifest),encoding='utf-8');before=path.read_bytes();out=tmp_path/'packet.json'
        pipeline.export_translation_command(argparse.Namespace(manifest=str(path),output=str(out)))
        packet=json.loads(out.read_text(encoding='utf-8'));packet['records'][0]['translation']='Rated power10 kW'
        if legacy:packet['records'][0].update(context_before='',context_after='')
        if change in ('source_sha256','source_language','target_language'):packet[change]='different'
        elif change=='source_text':packet['records'][0]['source_text']='Different source'
        else:packet['records'].append(dict(packet['records'][0]))
        out.write_text(json.dumps(packet),encoding='utf-8')
        with pytest.raises(SystemExit):pipeline.merge_translation_command(argparse.Namespace(manifest=str(path),packet=str(out),allow_cjk=False))
        assert path.read_bytes()==before

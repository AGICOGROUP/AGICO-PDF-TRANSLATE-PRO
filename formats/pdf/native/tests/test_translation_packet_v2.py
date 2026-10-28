import argparse
import importlib.util
import json
import sys
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[4]
spec=importlib.util.spec_from_file_location("v2_native_packet",ROOT/"formats/pdf/native/scripts/pdf_translation_pipeline.py")
pipeline=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=pipeline
spec.loader.exec_module(pipeline)


def job(tmp_path, target="en"):
    manifest={"source_sha256":"source", "source_language":"zh", "target_language":target,
              "pages":[{"page":1,"blocks":[{"id":"p1", "source_text":"窑头罩", "translation":""},
              {"id":"p2", "source_text":"80 W", "translation":""}]}]}
    path=tmp_path/"manifest.json";path.write_text(json.dumps(manifest),encoding="utf-8")
    return path,manifest


@pytest.mark.parametrize("records",[
    [{"id":"p1","source_text":"窑头罩","translation":"Kiln hood"},{"id":"p1","source_text":"窑头罩","translation":"Wrong duplicate"}],
    [{"id":"p1","source_text":"窑头罩","translation":None}],
    [{"id":"p1","source_text":"窑头罩","translation":123}],
])
def test_invalid_packet_never_overwrites_manifest(tmp_path,records):
    path,_=job(tmp_path);before=path.read_bytes()
    packet=tmp_path/"packet.json";packet.write_text(json.dumps({"source_sha256":"source","records":records}),encoding="utf-8")
    with pytest.raises(SystemExit):
        pipeline.merge_translation_command(argparse.Namespace(manifest=str(path),packet=str(packet),allow_cjk=False))
    assert path.read_bytes()==before


def test_target_chinese_does_not_require_unrelated_residue_override(tmp_path):
    path,_=job(tmp_path,"zh-CN")
    packet=tmp_path/"packet.json";packet.write_text(json.dumps({"source_sha256":"source","records":[{"id":"p1","source_text":"窑头罩","translation":"窑头罩"}]}),encoding="utf-8")
    pipeline.merge_translation_command(argparse.Namespace(manifest=str(path),packet=str(packet),allow_cjk=False))
    assert json.loads(path.read_text(encoding="utf-8"))["pages"][0]["blocks"][0]["translation"]=="窑头罩"


def test_export_carries_whole_page_context_and_term_senses_without_changing_source(tmp_path):
    path,_=job(tmp_path);before=path.read_bytes();out=tmp_path/"packet.json"
    pipeline.export_translation_command(argparse.Namespace(manifest=str(path),output=str(out)))
    packet=json.loads(out.read_text(encoding="utf-8"))
    assert packet["pages"][0]["ordered_source_ids"]==["p1","p2"]
    assert packet["pages"][0]["page_context"]=="窑头罩\n80 W"
    term=next(t for t in packet["pages"][0]["terminology"] if t["source"]=="窑头罩")
    assert term["translation"]=="Kiln hood" and "语境" in term["context"]
    assert packet["target_language"]=="en"
    assert path.read_bytes()==before


@pytest.mark.parametrize("field,value", [("source_language","es"),("target_language","ru")])
def test_packet_from_another_language_request_is_rejected(tmp_path,field,value):
    path,_=job(tmp_path);before=path.read_bytes()
    packet=tmp_path/"packet.json"
    payload={"source_sha256":"source",field:value,"records":[{"id":"p1","source_text":"窑头罩","translation":"Kiln hood"}]}
    packet.write_text(json.dumps(payload),encoding="utf-8")
    with pytest.raises(SystemExit,match="differs from manifest"):
        pipeline.merge_translation_command(argparse.Namespace(manifest=str(path),packet=str(packet),allow_cjk=False))
    assert path.read_bytes()==before

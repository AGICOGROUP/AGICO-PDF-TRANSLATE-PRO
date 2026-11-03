import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "formats/pdf/scripts"))


def test_english_alias_retains_context_and_all_ambiguous_candidates():
    from glossary_lookup import lookup_english
    entries = {"窑头罩": {"source": "窑头罩", "translation": "Kiln hood", "aliases": ["Firing hood"], "context": "燃烧区语境"},
               "燃烧罩": {"source": "燃烧罩", "translation": "Firing hood", "context": "须按设备判断"}}
    matches = lookup_english("  FIRING   HOOD ", entries)
    assert {m["source"] for m in matches} == {"窑头罩", "燃烧罩"}
    assert all(m["context"] for m in matches)


def test_english_scan_uses_word_boundaries_longest_match_and_aliases():
    from glossary_lookup import scan_english
    entries = {"冷却器": {"source": "冷却器", "translation": "cooler"},
               "篦冷机": {"source": "篦冷机", "translation": "Grate Cooler", "aliases": ["grate cooling machine"]}}
    text = "Grate Cooler; grate cooling machine. coolers."
    matches = scan_english(text, entries)
    assert [m["source"] for m in matches] == ["篦冷机", "篦冷机"]
    assert [text[m["start"]:m["end"]] for m in matches] == ["Grate Cooler", "grate cooling machine"]


def test_new_table_lookup_keeps_uncertain_records_out_of_index():
    from glossary_lookup import parse_glossary, lookup_english
    entries, history = parse_glossary(ROOT / "formats/pdf/scan/references/cement-terminology.md")
    assert len(entries) == 6141
    assert entries["套筒扳手"]["translation"] == "socket wrench"
    assert lookup_english("socket wrench", entries)[0]["source"] == "套筒扳手"
    assert not any(s.startswith("Word 原文：") for s in entries)


def test_unicode_case_variants_do_not_crash_english_matching():
    from glossary_lookup import scan_english
    entries={"窑头罩":{"source":"窑头罩","translation":"Kiln hood"}}
    text="KİLN HOOD / Kıln hood"
    matches=scan_english(text,entries)
    assert [m["source"] for m in matches]==["窑头罩","窑头罩"]


def test_page_hints_omit_weak_wrong_context_terms_but_keep_exact_lookup():
    from glossary_lookup import parse_glossary,page_terms,lookup_english
    entries,_=parse_glossary(ROOT/'formats/pdf/native/references/cement-terminology.md')
    hints=page_terms('Before inspection, isolate the supply. Close the discharge valve; stop if visible leakage occurs.',entries)
    assert not {'放电','管网漏失水量'} & {h['source'] for h in hints}
    assert lookup_english('discharge',entries), 'Conservative automatic hints must not delete explicit lookup senses'
    hints=page_terms('安装标高、温升及功率；试运行回转窑和篦冷机。',entries)
    assert not {'重','高'} & {h['source'] for h in hints}
    assert {'回转窑','篦冷机'} <= {h['source'] for h in hints}


def test_compact_page_hints_retain_all_cement_senses_and_semantic_context():
    from glossary_lookup import page_terms
    entries={
        '窑头罩':{'source':'窑头罩','translation':'Kiln hood','aliases':['Firing hood'],'line':1,'context':'燃烧区罩体语境'},
        '燃烧罩':{'source':'燃烧罩','translation':'Firing hood','line':2,'context':'须按设备判断'},
        '熟料输送机':{'source':'熟料输送机','translation':'Clinker conveyor','line':3,'context':'Word 参考资料原文（2011）；新增词条未经逐条专业校核，使用时结合语境核对。用于熟料输送。'},
    }
    hints=page_terms('Firing hood and Clinker conveyor',entries)
    assert {h['source'] for h in hints}==set(entries)
    assert all('line' not in h for h in hints)
    assert next(h for h in hints if h['source']=='熟料输送机')['context']=='用于熟料输送。'
    assert all(h.get('context') for h in hints)

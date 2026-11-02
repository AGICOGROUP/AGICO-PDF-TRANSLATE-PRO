from pathlib import Path
import sys
import pymupdf
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import native_cad_pipeline as pipeline


def test_empty_replay_list_does_not_load_xml(monkeypatch):
    import builtins
    original_import = builtins.__import__
    xml_imports = []

    def capture_import(name, *args, **kwargs):
        if name.startswith('xml.etree'):
            xml_imports.append(name)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', capture_import)
    pipeline.restore_preserved_native_glyphs(None, None, {}, {}, {})
    assert xml_imports == []


def test_preserved_native_brand_replayed_as_vectors_without_raster_resources(tmp_path):
    src=tmp_path/'source.pdf';d=pymupdf.open();p=d.new_page(width=300,height=200)
    p.insert_text((30,50),'BRAND',fontsize=24,color=(1,.2,0));d.save(src);d.close()
    target=pymupdf.open();target.new_page(width=300,height=200)
    records={'logo':{'id':'logo','page':0,'kind':'native','bbox':[28,25,130,58]}}
    inv={'reviewed_protected_native_replay':[{'id':'logo','note':'Fresh fixture logo source viewed'}]}
    pipeline.restore_preserved_native_glyphs(target,src,inv,records,{'logo':{'status':'preserved'}})
    assert not target[0].get_image_info()
    pix=target[0].get_pixmap(alpha=False)
    assert sum(pix.samples[i]>180 and pix.samples[i+1]<150 for i in range(0,len(pix.samples),3))>100

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]


class ImageAdapterContractTests(unittest.TestCase):
    def test_root_router_exposes_three_input_types(self):
        router = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("PNG", router)
        self.assertIn("JPEG", router)
        self.assertIn("formats/image/SKILL.md", router)

    def test_root_discovery_metadata_and_readme_include_images(self):
        metadata = (ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for content in (metadata, readme):
            self.assertIn("PNG", content)
            self.assertIn("JPEG", content)

    def test_image_adapter_reuses_raster_utilities_with_independent_gates(self):
        adapter = (ROOT / "formats" / "image" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("scan raster extraction/build utilities", adapter)
        self.assertIn("do not inherit", adapter)
        self.assertIn("same pixel dimensions", adapter)
        self.assertIn("same image format", adapter)
        for unsupported in ("GIF", "SVG", "multi-page TIFF"):
            self.assertIn(unsupported, adapter)

    def test_no_text_gate_completes_without_translation_output(self):
        adapter = (ROOT / "formats" / "image" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("translation_complete_no_text", adapter)
        self.assertIn("OCR finds zero", adapter)
        self.assertIn("full-image visual inspection", adapter)
        self.assertIn("Do not create a translated image or PDF", adapter)


if __name__ == "__main__":
    unittest.main()

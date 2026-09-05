from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from draft_blocks import group_page_lines


def line(
    line_id: str,
    text: str,
    box: list[float],
    *,
    rotation: int = 0,
    score: float = 0.96,
) -> dict:
    return {
        "id": line_id,
        "page": 1,
        "text": text,
        "box": box,
        "rotation": rotation,
        "score": score,
    }


class PageRegionGroupingTests(unittest.TestCase):
    def test_continuous_body_lines_join_one_region_with_glyph_boxes(self) -> None:
        groups = group_page_lines(
            [
                line("l1", "El acero se fabricara mediante un procedimiento", [100, 300, 900, 340]),
                line("l2", "aprobado por la entidad contratante y debera", [100, 350, 880, 390]),
                line("l3", "cumplir todos los requisitos indicados.", [100, 400, 720, 440]),
            ],
            page_height=1200,
        )
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["line_ids"], ["l1", "l2", "l3"])
        self.assertEqual(groups[0]["role"], "body")
        self.assertEqual(groups[0]["clean_boxes"], [[100.0, 300.0, 900.0, 340.0], [100.0, 350.0, 880.0, 390.0], [100.0, 400.0, 720.0, 440.0]])

    def test_numbered_heading_stays_separate_from_body(self) -> None:
        groups = group_page_lines(
            [
                line("h1", "II.3.- Elaboracion del acero.", [100, 250, 650, 295]),
                line("b1", "El procedimiento de elaboracion queda a eleccion", [100, 330, 900, 370]),
                line("b2", "del proveedor, sujeto a aprobacion.", [100, 380, 720, 420]),
            ],
            page_height=1200,
        )
        self.assertEqual([group["line_ids"] for group in groups], [["h1"], ["b1", "b2"]])
        self.assertEqual(groups[0]["role"], "heading")
        self.assertEqual(groups[1]["role"], "body")

    def test_two_columns_never_merge(self) -> None:
        groups = group_page_lines(
            [
                line("l1", "Primera columna continua", [80, 300, 500, 340]),
                line("r1", "Segunda columna continua", [650, 305, 1100, 345]),
                line("l2", "en la linea siguiente.", [80, 350, 480, 390]),
                line("r2", "en su propia linea.", [650, 355, 1050, 395]),
            ],
            page_height=1200,
        )
        self.assertEqual([group["line_ids"] for group in groups], [["l1", "l2"], ["r1", "r2"]])

    def test_header_footer_and_rotated_label_are_isolated(self) -> None:
        groups = group_page_lines(
            [
                line("header", "ESPECIFICACION TECNICA", [100, 20, 800, 60]),
                line("body1", "Texto principal de la pagina", [100, 260, 850, 300]),
                line("body2", "que continua en esta linea.", [100, 310, 760, 350]),
                line("rot", "BARRA GUIA", [1020, 400, 1080, 620], rotation=90),
                line("footer", "HOJA 6 DE 21", [800, 1130, 1100, 1170]),
            ],
            page_height=1200,
        )
        by_ids = {tuple(group["line_ids"]): group for group in groups}
        self.assertEqual(by_ids[("header",)]["role"], "header")
        self.assertEqual(by_ids[("body1", "body2")]["role"], "body")
        self.assertEqual(by_ids[("rot",)]["role"], "diagram_label")
        self.assertEqual(by_ids[("footer",)]["role"], "footer")

    def test_table_like_rows_do_not_merge_into_prose(self) -> None:
        groups = group_page_lines(
            [
                line("intro", "La composicion quimica sera la siguiente:", [100, 250, 850, 290]),
                line("row1", "C    0.60    0.80", [140, 330, 700, 370]),
                line("row2", "Mn   0.80    1.30", [140, 380, 700, 420]),
            ],
            page_height=1200,
        )
        self.assertEqual([group["line_ids"] for group in groups], [["intro"], ["row1"], ["row2"]])
        self.assertEqual(groups[1]["role"], "table_cell")
        self.assertEqual(groups[2]["role"], "table_cell")


if __name__ == "__main__":
    unittest.main()

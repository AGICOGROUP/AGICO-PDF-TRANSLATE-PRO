import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import contracts


@pytest.fixture(autouse=True)
def fixed_character_metrics(monkeypatch):
    monkeypatch.setattr(contracts, 'stringWidth', lambda text, font, size: len(text) * size)


def test_elevation_decimal_remains_one_token_inside_chinese():
    lines = contracts._wrap_paragraph('标高+463.00及设备', 'font', 10, 80)
    assert any('+463.00' in line for line in lines)
    assert ''.join(lines) == '标高+463.00及设备'


def test_latin_name_is_not_split_by_chinese_character_wrapping():
    lines = contracts._wrap_paragraph('设备Marmara公司', 'font', 10, 70)
    assert any('Marmara' in line for line in lines)
    assert ''.join(lines) == '设备Marmara公司'


def test_protected_overlong_model_requires_layout_repair_instead_of_split():
    with pytest.raises(contracts.TextOverflowError):
        contracts._wrap_paragraph('型号XFC580-T-RU', 'font', 10, 60)


def test_tolerance_sign_and_temperature_unit_stay_with_the_value():
    lines = contracts._wrap_paragraph('温差±13.5°C与压力', 'font', 10, 70)
    assert any('±13.5°C' in line for line in lines)


def test_single_character_celsius_unit_stays_with_value():
    lines = contracts._wrap_paragraph('\u6e29\u5dee35\u2103', 'font', 10, 40)
    assert lines == ['\u6e29\u5dee', '35\u2103']

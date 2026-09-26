import pytest

from nesting import nest


def test_scenario1_fits_150_per_sheet():
    layout = nest(200, 100, 50)
    assert layout["parts_per_sheet"] == 150
    assert layout["sheets_needed"] == 1
    assert layout["scrap_pct"] == 68.0


def test_picks_better_orientation():
    # 700 x 300: as given 1 x 8 = 8, rotated 4 x 3 = 12
    assert nest(700, 300, 12)["orientation"] == "rotated"
    assert nest(700, 300, 12)["parts_per_sheet"] == 12


def test_sheets_round_up():
    assert nest(200, 100, 151)["sheets_needed"] == 2


def test_part_larger_than_sheet():
    with pytest.raises(ValueError):
        nest(3000, 1300, 1)

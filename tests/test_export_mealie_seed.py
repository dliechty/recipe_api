import json

from migration_scripts.export_mealie_seed import (
    distinct_source_values,
    write_seed,
)


class _FakeClient:
    def list_foods(self):
        return [{"id": "1", "name": "Kale", "label": {"name": "Produce"}}]

    def list_units(self):
        return [{"id": "u1", "name": "cup", "abbreviation": "c"}]

    def list_labels(self):
        return [{"id": "l1", "name": "Produce"}]


def test_distinct_source_values_dedupes_and_sorts():
    rows = [("Kale", "Cup"), ("kale", "cup"), ("Egg", "Piece")]
    foods, units = distinct_source_values(rows)
    assert foods == ["Egg", "Kale", "kale"]   # case-sensitive distinct, sorted
    assert units == ["Cup", "Piece", "cup"]


def test_write_seed_writes_all_files(tmp_path):
    write_seed(_FakeClient(), [("Kale", "Cup")], tmp_path)
    assert json.loads((tmp_path / "foods.json").read_text())[0]["name"] == "Kale"
    assert json.loads((tmp_path / "units.json").read_text())[0]["name"] == "cup"
    assert json.loads((tmp_path / "labels.json").read_text())[0]["name"] == "Produce"
    assert (tmp_path / "source_foods.txt").read_text().splitlines() == ["Kale"]
    assert (tmp_path / "source_units.txt").read_text().splitlines() == ["Cup"]

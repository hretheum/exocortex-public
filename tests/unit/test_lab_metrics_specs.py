"""Existing behaviour of exocortex.lab.metrics and the file-only parts of exocortex.lab.specs."""

from __future__ import annotations

import pytest

from exocortex.lab import metrics, specs


def _rows(config: str, flags: list[tuple[bool, int | None]]) -> list[dict]:
    return [{"config": config, "item_id": f"i{n}", "ok": ok, "chars": 100 + n, "unit_chars": unit}
            for n, (ok, unit) in enumerate(flags)]


def test_toy_metrics_single_config_reports_mean_and_share():
    rows = _rows("a", [(True, 50), (True, 10), (False, None), (True, None)])
    out = {m["metric"]: m for m in metrics.toy_metrics(rows, "exp/run", long_unit=20)}
    assert set(out) == {"mean_chars", "long_unit_share"}
    assert out["mean_chars"]["result_id"] == "exp/run/a/mean_chars"
    assert out["mean_chars"]["n"] == 3  # the failed row is excluded
    assert out["long_unit_share"]["details"] == {"successes": 1}
    assert out["long_unit_share"]["value"] == pytest.approx(1 / 3)


def test_toy_metrics_two_configs_add_a_difference_row():
    rows = _rows("a", [(True, 50), (True, 50)]) + _rows("b", [(True, 5), (True, 5)])
    out = metrics.toy_metrics(rows, "exp/run", long_unit=20)
    diff = out[-1]
    assert diff["metric"] == "long_unit_share_difference"
    assert diff["details"] == {"a": "a", "b": "b", "difference": "b - a"}
    assert diff["value"] == pytest.approx(-1.0)
    assert diff["n"] == 2


def test_toy_metrics_is_independent_of_row_order():
    rows = _rows("a", [(True, 50), (True, 5), (True, 30)])
    assert metrics.toy_metrics(rows, "p", 20) == metrics.toy_metrics(list(reversed(rows)), "p", 20)


def test_specs_load_requires_the_documented_keys(tmp_path):
    good = tmp_path / "good.yaml"
    good.write_text("slug: s\nkind: toy\ntitle: T\nconfigs: []\nsamples: []\n", encoding="utf-8")
    assert specs.load(good)["slug"] == "s"
    bad = tmp_path / "bad.yaml"
    bad.write_text("slug: s\nkind: toy\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing title"):
        specs.load(bad)


class _Conn:
    def __init__(self, row):
        self._row = row

    def execute(self, *_args):
        return self

    def fetchone(self):
        return self._row


def test_preregistration_without_hypothesis_needs_nothing():
    assert specs.preregistration(_Conn(None), {}) == (None, None)


def test_preregistration_returns_version_and_checksum_when_frozen():
    spec = {"hypothesis": {"slug": "h", "version": "2"}}
    conn = _Conn({"prereg_sha256": "abc", "violated": False})
    assert specs.preregistration(conn, spec) == (2, "abc")


@pytest.mark.parametrize("row, message", [
    (None, "not frozen"),
    ({"prereg_sha256": None, "violated": False}, "not frozen"),
    ({"prereg_sha256": "abc", "violated": True}, "changed after it was frozen"),
])
def test_preregistration_refuses_unfrozen_or_violated(row, message):
    spec = {"hypothesis": {"slug": "h", "version": 1}}
    with pytest.raises(specs.NotPreregistered, match=message):
        specs.preregistration(_Conn(row), spec)

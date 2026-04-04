"""Tests for scripts/universe.py — UniverseConfig registry."""

from scripts.universe import get_universe_config, UniverseConfig, BENCHMARK_BY_UNIVERSE


def test_sp500_config():
    cfg = get_universe_config("sp500")
    assert isinstance(cfg, UniverseConfig)
    assert cfg.benchmark == "SPY"
    assert cfg.prices_dir.name == "prices"
    assert "sp500" in cfg.history_path.name


def test_russell2000_tech_config():
    cfg = get_universe_config("russell2000_tech")
    assert cfg.benchmark == "IWM"
    assert cfg.prices_dir.name == "prices_russell2000"
    assert "russell2000_tech" in cfg.history_path.name


def test_unknown_universe_raises():
    import pytest
    with pytest.raises(KeyError):
        get_universe_config("bogus_universe")


def test_benchmark_mapping():
    assert BENCHMARK_BY_UNIVERSE["sp500"] == "SPY"
    assert BENCHMARK_BY_UNIVERSE["russell2000_tech"] == "IWM"

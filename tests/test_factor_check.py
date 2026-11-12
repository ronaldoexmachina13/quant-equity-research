"""Tests for src/factor_check.py. Inputs are hand-made."""
import numpy as np
import pandas as pd
import pytest

from src.factor_check import (annualise_alpha, correlation_with_reference, read_french, regress_on_benchmark,
                              regress_on_factors)


def _months(n):
    return pd.date_range("2012-01-31", periods=n, freq="ME")


def test_regression_recovers_exact_alpha_and_beta():
    x = pd.Series(np.linspace(-0.05, 0.06, 40), index=_months(40))
    y = 0.002 + 1.3 * x
    out = regress_on_benchmark(y, x)
    assert out["alpha"] == pytest.approx(0.002, abs=1e-12)
    assert out["beta"] == pytest.approx(1.3, abs=1e-12)
    assert out["r_squared"] == pytest.approx(1.0)
    assert out["months"] == 40


def test_regression_matches_statsmodels_hac():
    sm = pytest.importorskip("statsmodels.api")
    rng = np.random.default_rng(1)
    x = pd.Series(rng.normal(0.01, 0.04, 80), index=_months(80))
    y = 0.001 + 0.9 * x + pd.Series(rng.normal(0, 0.02, 80), index=x.index)
    ours = regress_on_benchmark(y, x, lags=3)
    fit = sm.OLS(y.values, sm.add_constant(x.values)).fit(cov_type="HAC", cov_kwds={"maxlags": 3, "use_correction": False})
    assert ours["alpha"] == pytest.approx(fit.params[0])
    assert ours["beta"] == pytest.approx(fit.params[1])
    assert ours["alpha_se"] == pytest.approx(fit.bse[0], rel=1e-9)
    assert ours["beta_se"] == pytest.approx(fit.bse[1], rel=1e-9)


def test_regression_uses_only_common_months():
    x = pd.Series(np.linspace(-0.05, 0.06, 40), index=_months(40))
    y = (0.001 + x).iloc[5:]
    assert regress_on_benchmark(y, x)["months"] == 35


def test_regression_rejects_short_series():
    x = pd.Series(np.arange(5.0), index=_months(5))
    with pytest.raises(ValueError):
        regress_on_benchmark(x, x)


def test_annualise_alpha_is_twelve_times_monthly():
    assert annualise_alpha(0.001) == pytest.approx(0.012)


def test_correlation_of_identical_and_opposite_series():
    a = pd.Series(np.arange(30.0) ** 1.5, index=_months(30))
    assert correlation_with_reference(a, a)["pearson"] == pytest.approx(1.0)
    assert correlation_with_reference(a, -a)["spearman"] == pytest.approx(-1.0)


def test_correlation_interval_contains_estimate():
    rng = np.random.default_rng(2)
    a = pd.Series(rng.normal(size=60), index=_months(60))
    b = a * 0.5 + pd.Series(rng.normal(size=60), index=a.index)
    out = correlation_with_reference(a, b)
    assert out["pearson_lower"] < out["pearson"] < out["pearson_upper"]


def test_read_french_converts_percent_and_month_end(tmp_path):
    path = tmp_path / "f.csv"
    path.write_text("201201,1.50,-0.50\n201202,2.00,0.25\n")
    frame = read_french(str(path), ["a", "b"])
    assert list(frame.index) == [pd.Timestamp("2012-01-31"), pd.Timestamp("2012-02-29")]
    assert frame.loc["2012-01-31", "a"] == pytest.approx(0.015)
    assert frame.loc["2012-02-29", "b"] == pytest.approx(0.0025)


def _factors(n, seed=3):
    rng = np.random.default_rng(seed)
    return pd.DataFrame(rng.normal(0.005, 0.04, (n, 4)), index=_months(n), columns=["Mkt-RF", "SMB", "HML", "Mom"])


def test_factor_regression_recovers_exact_coefficients():
    f = _factors(60)
    y = 0.003 + 1.1 * f["Mkt-RF"] - 0.4 * f["SMB"] + 0.7 * f["HML"] + 0.2 * f["Mom"]
    out = regress_on_factors(y, f)
    assert out["alpha"] == pytest.approx(0.003, abs=1e-12)
    assert out["beta_Mkt-RF"] == pytest.approx(1.1, abs=1e-10)
    assert out["beta_SMB"] == pytest.approx(-0.4, abs=1e-10)
    assert out["beta_HML"] == pytest.approx(0.7, abs=1e-10)
    assert out["beta_Mom"] == pytest.approx(0.2, abs=1e-10)
    assert out["r_squared"] == pytest.approx(1.0)


def test_factor_regression_matches_statsmodels_hac():
    sm = pytest.importorskip("statsmodels.api")
    f = _factors(90, seed=5)
    rng = np.random.default_rng(6)
    y = 0.001 + 0.9 * f["Mkt-RF"] + 0.3 * f["HML"] + pd.Series(rng.normal(0, 0.02, 90), index=f.index)
    ours = regress_on_factors(y, f, lags=4)
    fit = sm.OLS(y.values, sm.add_constant(f.values)).fit(cov_type="HAC", cov_kwds={"maxlags": 4, "use_correction": False})
    assert ours["alpha"] == pytest.approx(fit.params[0], abs=1e-12)
    assert ours["alpha_se"] == pytest.approx(fit.bse[0], rel=1e-9)
    for i, name in enumerate(f.columns, start=1):
        assert ours[f"beta_{name}"] == pytest.approx(fit.params[i], abs=1e-12)
        assert ours[f"beta_{name}_se"] == pytest.approx(fit.bse[i], rel=1e-9)


def test_factor_regression_uses_only_common_months_and_needs_enough():
    f = _factors(40)
    y = (0.001 + f["Mkt-RF"]).iloc[5:]
    assert regress_on_factors(y, f)["months"] == 35
    with pytest.raises(ValueError):
        regress_on_factors(y.iloc[:12], f)

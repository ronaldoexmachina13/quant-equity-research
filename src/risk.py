import numpy as np
import pandas as pd

TRADING_PERIODS_PER_YEAR = 12  # we're working in monthly returns


def annualized_return(returns: pd.Series) -> float:
    """Compound monthly returns into an annualized rate."""
    total_return = (1 + returns).prod()
    n_years = len(returns) / TRADING_PERIODS_PER_YEAR
    return total_return ** (1 / n_years) - 1


def annualized_volatility(returns: pd.Series) -> float:
    """Annualize monthly return volatility."""
    return returns.std() * np.sqrt(TRADING_PERIODS_PER_YEAR)


def sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.02) -> float:
    """
    Sharpe ratio using a simple constant annual risk-free rate assumption.
    """
    ann_return = annualized_return(returns)
    ann_vol = annualized_volatility(returns)
    return (ann_return - risk_free_rate) / ann_vol


def max_drawdown(returns: pd.Series) -> float:
    """
    Largest peak-to-trough decline in cumulative value.
    Returns a negative number (e.g. -0.25 = a 25% drawdown).
    """
    cumulative = (1 + returns).cumprod()
    running_max = cumulative.cummax()
    drawdown = (cumulative - running_max) / running_max
    return drawdown.min()


def summarize_risk(returns: pd.Series, label: str) -> dict:
    return {
        "label": label,
        "annualized_return": annualized_return(returns),
        "annualized_volatility": annualized_volatility(returns),
        "sharpe_ratio": sharpe_ratio(returns),
        "max_drawdown": max_drawdown(returns),
    }
"""Small shared helpers (re-exported so tests and scripts have one import point)."""

from engine.explain import money, risk_level          # noqa: F401
from capture.extract import checks, line_items_check  # noqa: F401
from engine.payments import credibility_k             # noqa: F401


def pct(x: float, digits: int = 1) -> str:
    """0.237 -> '23.7%'."""
    return f"{x * 100:.{digits}f}%"

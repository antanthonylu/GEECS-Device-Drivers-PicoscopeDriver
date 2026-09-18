"""Shared plot-backend selection for the lab demo scripts.

Picks an interactive backend when a GUI toolkit is actually available and
falls back to the headless ``Agg`` backend otherwise (e.g. an SSH session
without X forwarding) — either way ``savefig`` always works, so there is
always a PNG to look at even when a pop-up window isn't possible.
"""

from __future__ import annotations


def select_backend() -> bool:
    """Pick a matplotlib backend; return whether it supports ``plt.show()``."""
    import matplotlib

    try:
        import tkinter  # noqa: F401

        matplotlib.use("TkAgg")
        return True
    except Exception:
        try:
            matplotlib.use("Agg")
        except Exception:
            pass
        return False

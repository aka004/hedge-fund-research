"""Verify `generate_ai_verdict` reads the indicator payload correctly.

Closes two bugs from the 2026-05-13 code review:

1. The function reads `indicators_data.get("groups", {})` but
   `get_all_indicators_data` returns the payload under the key
   "indicators". The verdict prompt was always sent with no indicator
   data — Claude got the signal-balance counts only and produced a
   verdict not grounded in any actual indicators.

2. The summary line referenced `ind['display_value']` but
   `refresh_indicator` emits the key `'display'`. Even after fixing
   #1, the loop would `KeyError` and the outer except would 500.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))


def _sample_indicators_payload() -> dict:
    """Shape matches `get_all_indicators_data()` real output."""
    return {
        "indicators": {
            "rates": {
                "label": "Rates",
                "color": "blue",
                "indicators": [
                    {
                        "id": "fedfunds",
                        "name": "Fed Funds Rate",
                        "display": "5.25%",
                        "signal": "hawkish",
                        "available": True,
                    }
                ],
            },
            "inflation": {
                "label": "Inflation",
                "color": "red",
                "indicators": [
                    {
                        "id": "cpi",
                        "name": "CPI YoY",
                        "display": "3.4%",
                        "signal": "neutral",
                        "available": True,
                    }
                ],
            },
        },
        "signal_balance": {
            "hawkish": 1,
            "dovish": 0,
            "neutral": 1,
            "total": 2,
            "regime": "HAWKISH",
        },
        "last_updated": "2026-05-13T00:00:00",
    }


class _FakeMessages:
    def __init__(self, captured: list):
        self._captured = captured

    def create(self, model, max_tokens, messages):  # noqa: ARG002
        self._captured.append(messages)
        resp = MagicMock()
        resp.content = [MagicMock(text="VERDICT: hawkish, watch CPI.")]
        return resp


class _FakeAnthropic:
    def __init__(self, captured: list):
        self.messages = _FakeMessages(captured)


def test_verdict_includes_indicator_names_in_prompt(monkeypatch):
    captured = []

    monkeypatch.setattr(
        "app.services.macro_service.anthropic",
        MagicMock(Anthropic=lambda api_key: _FakeAnthropic(captured)),
    )
    monkeypatch.setattr(
        "app.services.macro_service.get_anthropic_api_key",
        lambda: "sk-ant-fake",
    )
    # Bypass DB write of verdict cache.
    monkeypatch.setattr(
        "app.services.macro_service.persist_verdict",
        lambda **_: None,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.macro_service.get_db",
        lambda: MagicMock(__enter__=lambda s: MagicMock(), __exit__=lambda *a: None),
        raising=False,
    )

    from app.services.macro_service import generate_ai_verdict

    payload = _sample_indicators_payload()

    try:
        generate_ai_verdict(payload)
    except Exception:
        # If anything later in the function fails (cache write etc),
        # we still want to inspect what was sent to Claude.
        pass

    assert captured, "Claude was never called — prompt construction failed"
    prompt_text = captured[0][0]["content"]

    # If the bug is still present (`groups` lookup → empty), the prompt
    # would only contain the signal-balance line. We expect indicator
    # names to be in the prompt.
    assert "Fed Funds Rate" in prompt_text, (
        f"verdict prompt missing 'Fed Funds Rate' (probable groups-key bug);\n"
        f"prompt:\n{prompt_text}"
    )
    assert "CPI YoY" in prompt_text
    # And the display value (not literal "display_value" placeholder).
    assert (
        "5.25%" in prompt_text
    ), "display value missing — probable display_value key bug"

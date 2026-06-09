from datetime import date
from bot.commands.reclassify import deeprun_since


def test_deeprun_since_default_six_months():
    s = deeprun_since(date(2026, 6, 9), months=6)
    assert s == "2025/12/11"


def test_deeprun_since_custom_months():
    s = deeprun_since(date(2026, 6, 9), months=1)
    assert s == "2026/05/10"

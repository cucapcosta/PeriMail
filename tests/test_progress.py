from peribot.bot.progress import progress_bar


def test_progress_bar_zero():
    bar = progress_bar(0, 100)
    assert "0/100 (0%)" in bar
    assert "█" not in bar


def test_progress_bar_half():
    bar = progress_bar(50, 100, width=10)
    assert bar.startswith("█████░░░░░")
    assert "50/100 (50%)" in bar


def test_progress_bar_complete():
    bar = progress_bar(120, 120, width=10)
    assert bar.startswith("██████████")
    assert "120/120 (100%)" in bar


def test_progress_bar_empty_total():
    bar = progress_bar(0, 0)
    assert "0/0 (0%)" in bar


def test_progress_bar_clamps_overrun():
    bar = progress_bar(150, 100, width=10)
    assert bar.startswith("██████████")
    assert "100/100 (100%)" in bar

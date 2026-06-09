from perimail.db import Proposal
from bot.commands.proposals import format_proposal_text


def test_format_proposal_text():
    p = Proposal(id=1, name="Games", description="gaming related mail",
                 keywords=["steam", "epic"],
                 samples=[{"subject": "Steam sale", "message_id": "m1", "account_email": "a@b.c"},
                          {"subject": "Epic free game", "message_id": "m2", "account_email": "a@b.c"}],
                 status="pending", discord_message_id=None)
    text = format_proposal_text(p)
    assert "Games" in text
    assert "gaming related mail" in text
    assert "steam" in text
    assert "Steam sale" in text
    assert "Epic free game" in text

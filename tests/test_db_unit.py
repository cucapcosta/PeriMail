from peribot.core.db import Category, Proposal


def test_category_score_urgency_defaults_false():
    c = Category(id=1, name="X", label="PeriMail/X", description="",
                 keywords=[], header_triggers=[], applies_to="all")
    assert c.score_urgency is False


def test_proposal_dataclass_fields():
    p = Proposal(id=1, name="Games", description="game stuff",
                 keywords=["steam"], samples=[{"subject": "s", "message_id": "m", "account_email": "a@b.c"}],
                 status="pending", discord_message_id=None)
    assert p.name == "Games"
    assert p.samples[0]["message_id"] == "m"

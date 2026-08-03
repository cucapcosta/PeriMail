from unittest.mock import MagicMock
from peribot.mail.inferrer import infer
from peribot.mail.fetcher import EmailMessage


def _cat(name):
    from peribot.mail.db import Category
    return Category(id=1, name=name, label=f"PeriMail/{name}", description=f"{name} mail",
                    keywords=[], header_triggers=[], applies_to="all")


def _emails():
    return [
        EmailMessage(id="m1", subject="Steam summer sale", sender="news@steam.com", snippet="games"),
        EmailMessage(id="m2", subject="Your invoice", sender="billing@x.com", snippet="amount due"),
    ]


def _resp(text, in_tok=30, out_tok=20):
    r = MagicMock()
    r.text = text
    r.usage_metadata.prompt_token_count = in_tok
    r.usage_metadata.candidates_token_count = out_tok
    return r


def test_infer_returns_reassignments_and_proposals(mocker):
    payload = (
        '{"reassignments": [{"message_id": "m2", "category": "Useful"}], '
        '"proposals": [{"name": "Games", "description": "gaming mail", '
        '"keywords": ["steam","game"], "sample_message_ids": ["m1"]}]}'
    )
    client = MagicMock()
    client.models.generate_content.return_value = _resp(payload)
    mocker.patch("peribot.mail.inferrer.genai.Client", return_value=client)
    reassignments, proposals, usage = infer(_emails(), [_cat("Useful")], api_key="fake")
    assert reassignments == [{"message_id": "m2", "category": "Useful"}]
    assert proposals[0]["name"] == "Games"
    assert usage.input_tokens == 30


def test_infer_drops_reassignment_to_unknown_category(mocker):
    payload = '{"reassignments": [{"message_id": "m2", "category": "Ghost"}], "proposals": []}'
    client = MagicMock()
    client.models.generate_content.return_value = _resp(payload)
    mocker.patch("peribot.mail.inferrer.genai.Client", return_value=client)
    reassignments, proposals, usage = infer(_emails(), [_cat("Useful")], api_key="fake")
    assert reassignments == []


def test_infer_drops_proposal_colliding_with_existing(mocker):
    payload = '{"reassignments": [], "proposals": [{"name": "Useful", "description": "x", "keywords": [], "sample_message_ids": []}]}'
    client = MagicMock()
    client.models.generate_content.return_value = _resp(payload)
    mocker.patch("peribot.mail.inferrer.genai.Client", return_value=client)
    reassignments, proposals, usage = infer(_emails(), [_cat("Useful")], api_key="fake")
    assert proposals == []


def test_infer_empty_on_bad_json(mocker):
    client = MagicMock()
    client.models.generate_content.return_value = _resp("garbage")
    mocker.patch("peribot.mail.inferrer.genai.Client", return_value=client)
    reassignments, proposals, usage = infer(_emails(), [_cat("Useful")], api_key="fake")
    assert reassignments == [] and proposals == []

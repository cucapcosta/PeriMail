import pytest
from unittest.mock import MagicMock
from peribot.mail.classifier import classify_by_rules
from peribot.core.db import Category
from peribot.mail.fetcher import EmailMessage


def make_category(name, keywords=None, header_triggers=None, applies_to="all"):
    return Category(
        id=1, name=name, label=f"PeriMail/{name}",
        description=f"{name} emails",
        keywords=keywords or [],
        header_triggers=header_triggers or [],
        applies_to=applies_to,
    )


def make_email(subject="Hello", sender="sender@example.com", snippet="", headers=None):
    return EmailMessage(id="msg1", subject=subject, sender=sender, snippet=snippet, headers=headers or {})


def test_keyword_match_in_subject():
    cats = [make_category("Jobs", keywords=["internship"])]
    email = make_email(subject="Internship opportunity at Acme")
    assert classify_by_rules(email, cats) == "Jobs"


def test_keyword_match_case_insensitive():
    cats = [make_category("Jobs", keywords=["application received"])]
    email = make_email(subject="Application Received - Software Engineer")
    assert classify_by_rules(email, cats) == "Jobs"


def test_keyword_match_in_sender():
    cats = [make_category("Newsletter", keywords=["noreply"])]
    email = make_email(sender="noreply@company.com")
    assert classify_by_rules(email, cats) == "Newsletter"


def test_header_trigger_match():
    cats = [make_category("Newsletter", header_triggers=["List-Unsubscribe"])]
    email = make_email(headers={"List-Unsubscribe": "<mailto:unsub@example.com>"})
    assert classify_by_rules(email, cats) == "Newsletter"


def test_header_match_case_insensitive():
    cats = [make_category("Newsletter", header_triggers=["list-unsubscribe"])]
    email = make_email(headers={"List-Unsubscribe": "<mailto:unsub@example.com>"})
    assert classify_by_rules(email, cats) == "Newsletter"


def test_no_match_returns_none():
    cats = [make_category("Jobs", keywords=["internship"])]
    email = make_email(subject="Meeting tomorrow")
    assert classify_by_rules(email, cats) is None


def test_first_category_wins():
    cats = [
        make_category("Newsletter", keywords=["update"]),
        make_category("Jobs", keywords=["update"]),
    ]
    email = make_email(subject="Job update for you")
    assert classify_by_rules(email, cats) == "Newsletter"


from peribot.mail.classifier import classify, classify_with_gemini
from peribot.core.pricing import Usage


def _gemini_response(text, in_tok=10, out_tok=2):
    resp = MagicMock()
    resp.text = text
    resp.usage_metadata.prompt_token_count = in_tok
    resp.usage_metadata.candidates_token_count = out_tok
    return resp


def test_classify_uses_rules_first():
    cats = [make_category("Jobs", keywords=["internship"])]
    email = make_email(subject="Internship offer")
    category, method, usage = classify(email, cats, api_key="fake")
    assert category == "Jobs"
    assert method == "rules"
    assert usage.input_tokens == 0 and usage.output_tokens == 0


def test_classify_falls_back_to_gemini_when_no_rule_matches(mocker):
    cats = [make_category("Jobs", keywords=["internship"])]
    email = make_email(subject="Some unrelated subject")
    mocker.patch("peribot.mail.classifier.classify_with_gemini", return_value=("Useful", Usage(8, 1)))
    category, method, usage = classify(email, cats, api_key="fake")
    assert category == "Useful"
    assert method == "gemini"
    assert usage.input_tokens == 8


def test_classify_with_gemini_returns_valid_category(mocker):
    cats = [make_category("Jobs"), make_category("Newsletter")]
    email = make_email(subject="We received your application")
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _gemini_response("Jobs")
    mocker.patch("peribot.mail.classifier.genai.Client", return_value=mock_client)
    result, usage = classify_with_gemini(email, cats, api_key="fake_key")
    assert result == "Jobs"
    assert usage.input_tokens == 10 and usage.output_tokens == 2


def test_classify_with_gemini_returns_unclassified_on_invalid_response(mocker):
    cats = [make_category("Jobs")]
    email = make_email(subject="Something")
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _gemini_response("WeirdResponse")
    mocker.patch("peribot.mail.classifier.genai.Client", return_value=mock_client)
    result, usage = classify_with_gemini(email, cats, api_key="fake_key")
    assert result == "Unclassified"


def test_classify_with_gemini_retries_on_exception(mocker):
    cats = [make_category("Jobs")]
    email = make_email(subject="Something")
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [Exception("API error")] * 3
    mocker.patch("peribot.mail.classifier.genai.Client", return_value=mock_client)
    mocker.patch("time.sleep")
    result, usage = classify_with_gemini(email, cats, api_key="fake_key")
    assert result == "Unclassified"
    assert mock_client.models.generate_content.call_count == 3
    assert usage.input_tokens == 0

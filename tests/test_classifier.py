import pytest
from unittest.mock import MagicMock
from perimail.classifier import classify_by_rules
from perimail.db import Category
from perimail.fetcher import EmailMessage


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


# append to tests/test_classifier.py
from perimail.classifier import classify, classify_with_gemini


def test_classify_uses_rules_first():
    cats = [make_category("Jobs", keywords=["internship"])]
    email = make_email(subject="Internship offer")
    category, method = classify(email, cats, api_key="fake")
    assert category == "Jobs"
    assert method == "rules"


def test_classify_falls_back_to_gemini_when_no_rule_matches(mocker):
    cats = [make_category("Jobs", keywords=["internship"])]
    email = make_email(subject="Some unrelated subject")
    mocker.patch("perimail.classifier.classify_with_gemini", return_value="Useful")
    category, method = classify(email, cats, api_key="fake")
    assert category == "Useful"
    assert method == "gemini"


def test_classify_with_gemini_returns_valid_category(mocker):
    cats = [make_category("Jobs"), make_category("Newsletter")]
    email = make_email(subject="We received your application")

    mock_model = MagicMock()
    mock_model.generate_content.return_value.text = "Jobs"
    mocker.patch("google.generativeai.GenerativeModel", return_value=mock_model)
    mocker.patch("google.generativeai.configure")

    result = classify_with_gemini(email, cats, api_key="fake_key")
    assert result == "Jobs"


def test_classify_with_gemini_returns_unclassified_on_invalid_response(mocker):
    cats = [make_category("Jobs")]
    email = make_email(subject="Something")

    mock_model = MagicMock()
    mock_model.generate_content.return_value.text = "WeirdResponse"
    mocker.patch("google.generativeai.GenerativeModel", return_value=mock_model)
    mocker.patch("google.generativeai.configure")

    result = classify_with_gemini(email, cats, api_key="fake_key")
    assert result == "Unclassified"


def test_classify_with_gemini_retries_on_exception(mocker):
    cats = [make_category("Jobs")]
    email = make_email(subject="Something")

    mock_model = MagicMock()
    mock_model.generate_content.side_effect = [Exception("API error"), Exception("API error"), Exception("API error")]
    mocker.patch("google.generativeai.GenerativeModel", return_value=mock_model)
    mocker.patch("google.generativeai.configure")
    mocker.patch("time.sleep")

    result = classify_with_gemini(email, cats, api_key="fake_key")
    assert result == "Unclassified"
    assert mock_model.generate_content.call_count == 3

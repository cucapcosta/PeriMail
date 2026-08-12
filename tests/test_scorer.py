from unittest.mock import MagicMock
from peribot.mail.scorer import score_urgency
from peribot.mail.fetcher import EmailMessage


def _email():
    return EmailMessage(id="m1", subject="Server down", sender="ops@x.com", snippet="prod outage")


def _resp(text, in_tok=12, out_tok=5):
    r = MagicMock()
    r.text = text
    r.usage_metadata.prompt_token_count = in_tok
    r.usage_metadata.candidates_token_count = out_tok
    return r


def test_score_parses_json(mocker):
    client = MagicMock()
    client.models.generate_content.return_value = _resp('{"score": 5, "reason": "prod outage"}')
    mocker.patch("google.genai.Client", return_value=client)
    score, reason, usage = score_urgency(_email(), api_key="fake")
    assert score == 5
    assert "outage" in reason
    assert usage.input_tokens == 12 and usage.output_tokens == 5


def test_score_handles_code_fenced_json(mocker):
    client = MagicMock()
    client.models.generate_content.return_value = _resp('```json\n{"score": 3, "reason": "ok"}\n```')
    mocker.patch("google.genai.Client", return_value=client)
    score, reason, usage = score_urgency(_email(), api_key="fake")
    assert score == 3


def test_score_clamps_out_of_range(mocker):
    client = MagicMock()
    client.models.generate_content.return_value = _resp('{"score": 9, "reason": "x"}')
    mocker.patch("google.genai.Client", return_value=client)
    score, reason, usage = score_urgency(_email(), api_key="fake")
    assert score == 5


def test_score_returns_none_on_bad_json(mocker):
    client = MagicMock()
    client.models.generate_content.return_value = _resp("not json at all")
    mocker.patch("google.genai.Client", return_value=client)
    score, reason, usage = score_urgency(_email(), api_key="fake")
    assert score is None


def test_score_returns_none_on_persistent_error(mocker):
    client = MagicMock()
    client.models.generate_content.side_effect = [Exception("x")] * 3
    mocker.patch("google.genai.Client", return_value=client)
    mocker.patch("time.sleep")
    score, reason, usage = score_urgency(_email(), api_key="fake")
    assert score is None
    assert usage.input_tokens == 0

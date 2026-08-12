import json
import re
import time

from peribot.core import pricing
from peribot.core.pricing import Usage
from peribot.mail.fetcher import EmailMessage


def _extract_json(text: str) -> dict:
    cleaned = text.strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise ValueError("no JSON object found")
    return json.loads(match.group(0))


def score_urgency(email: EmailMessage, api_key: str) -> tuple:
    """Returns (score:int|None, reason:str, Usage). score is 1-5 or None on failure."""
    from google import genai  # lazy: keeps google-genai out of the idle bot's memory
    client = genai.Client(api_key=api_key)
    prompt = (
        "Rate the urgency/importance of this email on a scale of 1 to 5 "
        "(5 = most urgent/important, requires prompt attention; 1 = trivial).\n"
        f"Subject: {email.subject}\nFrom: {email.sender}\nSnippet: {email.snippet[:200]}\n\n"
        'Respond with ONLY a JSON object: {"score": <1-5>, "reason": "<short reason>"}'
    )
    for attempt in range(3):
        try:
            response = client.models.generate_content(model=pricing.MODEL, contents=prompt)
            usage = Usage(
                input_tokens=getattr(response.usage_metadata, "prompt_token_count", 0) or 0,
                output_tokens=getattr(response.usage_metadata, "candidates_token_count", 0) or 0,
            )
            data = _extract_json(response.text)
            score = int(data["score"])
            score = max(1, min(5, score))
            reason = str(data.get("reason", ""))
            return score, reason, usage
        except Exception:
            if attempt < 2:
                time.sleep(2 ** attempt)
    return None, "", Usage()

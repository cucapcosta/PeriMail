import json
import re
import time

from google import genai

from peribot.core import pricing
from peribot.core.pricing import Usage


def _extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text.strip(), re.DOTALL)
    if not match:
        raise ValueError("no JSON object found")
    return json.loads(match.group(0))


def infer(unclassified_emails: list, existing_categories: list, api_key: str) -> tuple:
    """
    One Gemini call over the unclassified batch.
    Returns (reassignments, proposals, Usage):
      reassignments: [{message_id, category}] into EXISTING categories
      proposals:     [{name, description, keywords, sample_message_ids}] for NEW categories
    """
    client = genai.Client(api_key=api_key)
    existing_names = {c.name for c in existing_categories}
    cat_list = "\n".join(f"- {c.name}: {c.description}" for c in existing_categories)
    email_list = "\n".join(
        f'  {{"message_id": "{e.id}", "subject": {json.dumps(e.subject)}, "from": {json.dumps(e.sender)}}}'
        for e in unclassified_emails
    )
    prompt = (
        "These emails could not be classified into existing categories.\n\n"
        f"Existing categories:\n{cat_list}\n\n"
        f"Unclassified emails:\n[{email_list}]\n\n"
        "Two tasks:\n"
        "1. reassignments: any email that actually fits an EXISTING category — list its message_id and that category name.\n"
        "2. proposals: for the remaining emails, propose up to 3 NEW categories that capture clusters. "
        "Each proposal: a short name (one or two words, not matching an existing category), a description, "
        "keyword list, and the sample_message_ids it covers.\n\n"
        'Respond with ONLY JSON: {"reassignments": [{"message_id": "...", "category": "..."}], '
        '"proposals": [{"name": "...", "description": "...", "keywords": ["..."], "sample_message_ids": ["..."]}]}'
    )
    for attempt in range(3):
        try:
            response = client.models.generate_content(model=pricing.MODEL, contents=prompt)
            usage = Usage(
                input_tokens=getattr(response.usage_metadata, "prompt_token_count", 0) or 0,
                output_tokens=getattr(response.usage_metadata, "candidates_token_count", 0) or 0,
            )
            data = _extract_json(response.text)
            reassignments = [
                r for r in data.get("reassignments", [])
                if isinstance(r, dict) and r.get("category") in existing_names and r.get("message_id")
            ]
            proposals = [
                p for p in data.get("proposals", [])
                if isinstance(p, dict) and p.get("name") and p["name"] not in existing_names
            ]
            return reassignments, proposals, usage
        except Exception:
            if attempt < 2:
                time.sleep(2 ** attempt)
    return [], [], Usage()

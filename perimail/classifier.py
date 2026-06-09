import time

from google import genai

from perimail import pricing
from perimail.pricing import Usage
from perimail.fetcher import EmailMessage

UNCLASSIFIED = "Unclassified"


def classify_by_rules(email: EmailMessage, categories: list) -> str | None:
    email_headers_lower = {k.lower() for k in email.headers}
    text = f"{email.subject} {email.sender}".lower()
    for category in categories:
        for header in category.header_triggers:
            if header.lower() in email_headers_lower:
                return category.name
        for keyword in category.keywords:
            if keyword.lower() in text:
                return category.name
    return None


def classify_with_gemini(email: EmailMessage, categories: list, api_key: str) -> tuple:
    """Returns (category_name, Usage)."""
    client = genai.Client(api_key=api_key)
    category_list = "\n".join(f"- {cat.name}: {cat.description}" for cat in categories)
    prompt = (
        "You are an email classifier. Classify the following email into exactly one of these categories:\n"
        f"{category_list}\n\n"
        f"Email:\nSubject: {email.subject}\nFrom: {email.sender}\n"
        f"Snippet: {email.snippet[:200]}\n\n"
        "Respond with only the category name, nothing else."
    )
    valid_names = {cat.name for cat in categories}

    for attempt in range(3):
        try:
            response = client.models.generate_content(model=pricing.MODEL, contents=prompt)
            usage = Usage(
                input_tokens=getattr(response.usage_metadata, "prompt_token_count", 0) or 0,
                output_tokens=getattr(response.usage_metadata, "candidates_token_count", 0) or 0,
            )
            result = response.text.strip()
            if result in valid_names:
                return result, usage
            for name in valid_names:
                if name.lower() == result.lower():
                    return name, usage
            return UNCLASSIFIED, usage
        except Exception:
            if attempt < 2:
                time.sleep(2 ** attempt)
    return UNCLASSIFIED, Usage()


def classify(email: EmailMessage, categories: list, api_key: str) -> tuple:
    """Returns (category_name, method, Usage) where method is 'rules' or 'gemini'."""
    result = classify_by_rules(email, categories)
    if result:
        return result, "rules", Usage()
    category, usage = classify_with_gemini(email, categories, api_key)
    return category, "gemini", usage

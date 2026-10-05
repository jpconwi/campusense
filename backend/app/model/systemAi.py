"""
model/systemAi.py - the Hugging Face connection.

Only this file talks to the language model. Everything else (faculty
availability, forms, reports, admin data) is handled by normal code.
"""

from app import config

_client = None


def _get_client():
    global _client
    if _client is None:
        from huggingface_hub import InferenceClient
        _client = InferenceClient(api_key=config.API_KEY, provider="auto")
    return _client


def ask_model(system_prompt, question):
    """Return the model's answer text, or None if it failed."""
    if not config.API_KEY or not config.MODEL:
        print("AI ERROR: MODEL or API_KEY is missing in backend/.env")
        return None
    try:
        response = _get_client().chat.completions.create(
            model=config.MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            max_tokens=500,
        )
        answer = (response.choices[0].message.content or "").strip()
        return answer or None
    except Exception as error:
        print("AI ERROR:", repr(error))
        return None


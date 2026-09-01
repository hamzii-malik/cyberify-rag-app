"""The chat model. It only ever sees the prompt we build for it."""

from openai import OpenAI

from app.config import OPENAI_API_KEY, CHAT_MODEL

client = OpenAI(api_key=OPENAI_API_KEY)


def chat(system_prompt: str, user_prompt: str) -> str:
    response = client.chat.completions.create(
        model=CHAT_MODEL,       # gpt-4o-mini, set in .env
        temperature=0,          # we want the same answer for the same context
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response.choices[0].message.content.strip()

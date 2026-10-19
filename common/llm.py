import os

from openai import AsyncOpenAI


class SharedLLMClient:
    def __init__(self):
        self.is_mock = os.getenv("LLM_MOCK", "false").lower() == "true"
        if not self.is_mock:
            self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    async def get_response(self, prompt: str) -> str:
        if self.is_mock:
            return f"[MOCK MODE] Mock AI response for prompt: {prompt[:30]}..."

        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], temperature=0.2
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"LLM Error: {str(e)}"


llm_client = SharedLLMClient()

"""Shared OpenAI client (Member A). Every OpenAI call in the project goes through this module.

TODO: LLMClient with mock mode (LLM_MOCK=true returns canned JSON), 20 s timeout, 2 retries,
and token-usage logging. See the OpenAI section of the team plan.
"""

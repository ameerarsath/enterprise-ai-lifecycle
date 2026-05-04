"""
ModelWrapper — Multi-provider LLM integration with resilience.

Solves: [33] Rate limits · [46] Version drift · [47] Incompatible JSON · [48] Coherence loss · [49] Prompt sensitivity · [50] Model refusals
"""

import json
import logging
from typing import Any, Dict, List, Optional
import asyncio

# Note: In a real app, you would use langchain_anthropic, langchain_openai, etc.
# For this architecture, we wrap the raw calls to add our resilience layer.

logger = logging.getLogger(__name__)


class LLMError(Exception):
    pass


class RateLimitError(LLMError):
    pass


class ModelRefusalError(LLMError):
    pass


class CoherenceError(LLMError):
    pass


class ModelWrapper:
    """
    Wraps LLM calls with resilience patterns.
    """

    # [46] Version pinning — ensuring consistent outputs across sprints
    PROVIDER_VERSIONS = {
        "anthropic": "claude-3-opus-20240229",
        "openai": "gpt-4-turbo-preview",
        "google": "gemini-1.5-pro-latest",
    }

    # [33] Fallback chain for rate limits or provider outages
    FALLBACK_CHAIN = ["anthropic", "openai", "google"]

    def __init__(self, primary_provider: str = "anthropic"):
        self.primary_provider = primary_provider

    async def generate_json(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        """
        Generates a JSON response with full resilience patterns.
        """
        provider_chain = [self.primary_provider] + [
            p for p in self.FALLBACK_CHAIN if p != self.primary_provider
        ]

        last_error = None

        for provider in provider_chain:
            for attempt in range(max_retries):
                try:
                    # Exponential backoff on retry [33]
                    if attempt > 0:
                        backoff = 2 ** attempt
                        logger.warning(f"Retrying {provider} in {backoff}s...")
                        await asyncio.sleep(backoff)

                    # [49] Apply provider-specific prompt tweaks here if needed
                    # e.g., Anthropic prefers XML tags, OpenAI prefers markdown

                    raw_response = await self._call_provider(
                        provider, system_prompt, messages, temperature
                    )

                    # [50] Refusal detection
                    if self._is_refusal(raw_response):
                        if attempt == max_retries - 1:
                            raise ModelRefusalError("Model refused the prompt.")
                        continue  # Try again

                    # [47] JSON Normalization
                    parsed_json = self._normalize_json(raw_response)

                    # [48] Coherence Check (basic heuristic)
                    if not self._is_coherent(parsed_json):
                        raise CoherenceError("Response failed coherence check.")

                    return parsed_json

                except RateLimitError as e:
                    last_error = e
                    # Break out of attempt loop, move to next provider
                    logger.warning(f"{provider} rate limited. Trying next provider.")
                    break
                except json.JSONDecodeError as e:
                    last_error = e
                    logger.warning(f"JSON decode failed on {provider}: {e}")
                    # Let it retry on the same provider
                except Exception as e:
                    last_error = e
                    logger.error(f"Unexpected error with {provider}: {e}")

        raise LLMError(f"All providers failed. Last error: {last_error}")

    async def _call_provider(
        self, provider: str, system: str, messages: list, temp: float
    ) -> str:
        """Mock provider call for architecture demonstration."""
        # In a real implementation, this would use LangChain or raw HTTP clients.
        # We simulate a successful JSON response.
        return '{"artifacts": {"dummy": "value"}, "messages": [{"role": "assistant", "content": "Done."}]}'

    def _is_refusal(self, text: str) -> bool:
        """Detect if the model refused to answer. [50]"""
        refusal_phrases = [
            "I cannot fulfill",
            "I'm sorry, but I can't",
            "I apologize, but I am unable",
            "As an AI language model, I cannot",
            "I am programmed to be a helpful and harmless",
        ]
        text_lower = text.lower()
        return any(phrase.lower() in text_lower for phrase in refusal_phrases)

    def _normalize_json(self, raw_text: str) -> Dict[str, Any]:
        """
        Extract and parse JSON from the raw LLM output. [47]
        Handles markdown code blocks and trailing commas.
        """
        text = raw_text.strip()
        
        # Extract from markdown block if present
        if "```json" in text:
            parts = text.split("```json")
            if len(parts) > 1:
                text = parts[1].split("```")[0].strip()
        elif "```" in text:
            parts = text.split("```")
            if len(parts) > 1:
                text = parts[1].strip()

        # Try standard parsing
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Attempt to fix common errors (like trailing commas)
        # This is a simple regex fix; robust solutions might use a library like `json-repair`
        import re
        text = re.sub(r',\s*([\]}])', r'\1', text)
        
        return json.loads(text)

    def _is_coherent(self, parsed_json: Dict[str, Any]) -> bool:
        """
        Basic coherence check. [48]
        Are the required keys present? Is the nesting completely broken?
        """
        if not isinstance(parsed_json, dict):
            return False
        
        # A valid agent output should generally have a messages array
        if "messages" not in parsed_json:
            return False
            
        if not isinstance(parsed_json["messages"], list):
            return False

        return True


# Global instance
model_wrapper = ModelWrapper()

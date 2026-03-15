"""
Nebius AI Provider for Video-to-Code.
Based on Libra's providers.ts architecture.
"""

import os
from openai import OpenAI
from typing import Generator, Any

_NEBIUS_BASE_URL = "https://api.studio.nebius.com/v1/"
_NEBIUS_MODEL = "Qwen/Qwen3-235B-A22B-Instruct-2507"
_NEBIUS_VISION_MODEL = "Qwen/Qwen2.5-VL-72B-Instruct"


class NebiusProvider:
    """Nebius AI provider for chat and vision tasks."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("NEBIUS_API_KEY")
        if not self.api_key:
            raise ValueError("NEBIUS_API_KEY is required")
        self.client = OpenAI(base_url=_NEBIUS_BASE_URL, api_key=self.api_key)

    def chat(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 8192,
        stream: bool = True,
    ) -> Generator[str, None, None]:
        """
        Stream chat completion.

        Args:
            messages: List of message dictionaries
            system_prompt: Optional system prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            stream: Whether to stream the response

        Yields:
            Text chunks from the model
        """
        all_messages = []
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        all_messages.extend(messages)

        response = self.client.chat.completions.create(
            model=_NEBIUS_MODEL,
            messages=all_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream,
        )

        if stream:
            for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        else:
            yield response.choices[0].message.content

    def chat_complete(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 8192,
    ) -> str:
        """
        Non-streaming chat completion.

        Args:
            messages: List of message dictionaries
            system_prompt: Optional system prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Returns:
            Complete response text
        """
        all_messages = []
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        all_messages.extend(messages)

        response = self.client.chat.completions.create(
            model=_NEBIUS_MODEL,
            messages=all_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        )

        return response.choices[0].message.content

    def vision_chat(
        self,
        image_base64: str,
        prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 4000,
    ) -> str:
        """
        Single image analysis with vision model.

        Args:
            image_base64: Base64-encoded image
            prompt: Prompt for vision analysis
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Returns:
            Model's response text
        """
        client = OpenAI(base_url=_NEBIUS_BASE_URL, api_key=self.api_key)

        response = client.chat.completions.create(
            model=_NEBIUS_VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}",
                            },
                        },
                        {
                            "type": "text",
                            "text": prompt,
                        },
                    ],
                }
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        )

        return response.choices[0].message.content

    def vision_chat_json(
        self,
        image_base64: str,
        prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 4000,
    ) -> dict:
        """
        Single image analysis with vision model, returning parsed JSON.

        Args:
            image_base64: Base64-encoded image
            prompt: Prompt for vision analysis
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Returns:
            Parsed JSON response
        """
        import json

        result = self.vision_chat(image_base64, prompt, temperature, max_tokens)

        if not result or not result.strip():
            raise ValueError("Empty response from vision API")

        # Parse JSON from response (handle markdown code blocks)
        text = result.strip()

        # Try to extract JSON from markdown code blocks
        if "```" in text:
            import re

            json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
            if json_match:
                text = json_match.group(1).strip()

        # Try to parse
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            # If direct parse fails, try to find JSON in the text
            import re

            json_match = re.search(r"\{[\s\S]*\}", text)
            if json_match:
                return json.loads(json_match.group(0))
            raise ValueError(f"Failed to parse JSON: {e}. Response: {text[:200]}")


def get_provider(api_key: str | None = None) -> NebiusProvider:
    """
    Get Nebius provider instance.

    Args:
        api_key: Optional API key override

    Returns:
        NebiusProvider instance
    """
    return NebiusProvider(api_key)

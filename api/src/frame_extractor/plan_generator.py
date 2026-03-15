"""
Plan Generation Module for Video-to-Code.
"""

from typing import Any, Generator

from .providers import get_provider
from .prompts import VIDEO_TO_CODE_SYSTEM_PROMPT
from .context_builder import build_user_prompt
from .parser import parse_plan_xml, Plan


def generate_plan_from_analyses(
    analyses: list[dict[str, Any]],
    api_key: str,
    user_message: str | None = None,
    temperature: float = 0.7,
) -> str:
    """
    Generate a plan from image analyses (Libra-style).

    Args:
        analyses: List of image analysis dictionaries
        api_key: Nebius API key
        user_message: Optional additional user message
        temperature: Sampling temperature

    Returns:
        XML plan string with <plan> structure
    """
    # Build user prompt from analyses
    user_prompt = build_user_prompt(analyses, user_message)

    # Get provider and generate
    provider = get_provider(api_key)

    # Stream the response
    full_response = ""
    for chunk in provider.chat(
        messages=[{"role": "user", "content": user_prompt}],
        system_prompt=VIDEO_TO_CODE_SYSTEM_PROMPT,
        temperature=temperature,
        stream=True,
    ):
        full_response += chunk

    return full_response


def generate_plan_streaming(
    analyses: list[dict[str, Any]],
    api_key: str,
    user_message: str | None = None,
    temperature: float = 0.7,
) -> Generator[str, None, None]:
    """
    Generate plan with streaming.

    Yields:
        Streaming XML chunks
    """
    user_prompt = build_user_prompt(analyses, user_message)

    provider = get_provider(api_key)

    for chunk in provider.chat(
        messages=[{"role": "user", "content": user_prompt}],
        system_prompt=VIDEO_TO_CODE_SYSTEM_PROMPT,
        temperature=temperature,
        stream=True,
    ):
        yield chunk


def generate_plan_parsed(
    analyses: list[dict[str, Any]],
    api_key: str,
    user_message: str | None = None,
    temperature: float = 0.7,
) -> Plan:
    """
    Generate plan and return parsed Plan object.

    Args:
        analyses: List of image analysis dictionaries
        api_key: Nebius API key
        user_message: Optional additional user message
        temperature: Sampling temperature

    Returns:
        Parsed Plan object
    """
    plan_xml = generate_plan_from_analyses(analyses, api_key, user_message, temperature)
    return parse_plan_xml(plan_xml)


def generate_plan_with_analyses(
    image_paths: list[str],
    api_key: str,
    user_message: str | None = None,
) -> dict[str, Any]:
    """
    Complete pipeline: analyze images + generate plan.

    Args:
        image_paths: List of paths to image files
        api_key: Nebius API key
        user_message: Optional additional user message

    Returns:
        Dictionary with analyses and plan
    """
    from .image_analyzer import analyze_images_batch

    # Step 1: Analyze images
    analyses = analyze_images_batch(image_paths, api_key)

    # Step 2: Generate plan
    plan = generate_plan_parsed(analyses, api_key, user_message)

    return {
        "analyses": analyses,
        "plan_xml": None,  # XML is not returned to save memory
        "thinking": plan.thinking,
        "plan_description": plan.plan_description,
        "checklist": plan.checklist,
    }

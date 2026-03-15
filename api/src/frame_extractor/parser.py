"""
XML Parser for Plan responses.
"""

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class ChecklistItem:
    """Represents a single checklist item."""

    id: str
    status: str  # "pending" | "in_progress" | "done"
    category: str  # "ui" | "dev" | "content"
    page: str  # Page number
    description: str


@dataclass
class Plan:
    """Represents a parsed plan from AI response."""

    thinking: str
    plan_description: str
    checklist: list[ChecklistItem]


def _extract_cdata_content(xml_text: str, tag_name: str) -> str:
    """Extract content from CDATA or regular tag."""
    # Match CDATA section
    pattern = rf"<{tag_name}><!\[CDATA\[(.*?)\]\]></{tag_name}>"
    match = re.search(pattern, xml_text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()

    # Match regular tag
    pattern = rf"<{tag_name}>(.*?)</{tag_name}>"
    match = re.search(pattern, xml_text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()

    return ""


def _extract_items(xml_text: str) -> list[dict]:
    """Extract checklist items from XML."""
    items = []

    # Find all <item> tags with their attributes
    item_pattern = r"<item([^>]*)>(.*?)</item>"
    for match in re.finditer(item_pattern, xml_text, re.DOTALL):
        attrs_str = match.group(1)
        content = match.group(2).strip()

        # Parse attributes
        attrs = {}
        id_match = re.search(r'id="([^"]*)"', attrs_str)
        if id_match:
            attrs["id"] = id_match.group(1)

        status_match = re.search(r'status="([^"]*)"', attrs_str)
        if status_match:
            attrs["status"] = status_match.group(1)

        category_match = re.search(r'category="([^"]*)"', attrs_str)
        if category_match:
            attrs["category"] = category_match.group(1)

        page_match = re.search(r'page="([^"]*)"', attrs_str)
        if page_match:
            attrs["page"] = page_match.group(1)

        # Extract description from CDATA or regular content
        desc_match = re.search(r"<!\[CDATA\[(.*?)\]\]>", content, re.DOTALL)
        if desc_match:
            attrs["description"] = desc_match.group(1).strip()
        else:
            attrs["description"] = content.strip()

        items.append(attrs)

    return items


def parse_plan_xml(xml_response: str) -> Plan:
    """
    Parse XML response into Plan object.

    Args:
        xml_response: Raw XML string from AI

    Returns:
        Plan object with thinking, planDescription, and checklist

    Raises:
        ValueError: If XML is invalid or missing required tags
    """
    if not xml_response or "<plan>" not in xml_response:
        raise ValueError("Invalid response: missing <plan> tag")

    # Extract thinking
    thinking = _extract_cdata_content(xml_response, "thinking")

    # Extract planDescription
    plan_description = _extract_cdata_content(xml_response, "planDescription")

    # Extract checklist items
    checklist = []
    items_data = _extract_items(xml_response)

    for item in items_data:
        checklist.append(
            ChecklistItem(
                id=item.get("id", ""),
                status=item.get("status", "pending"),
                category=item.get("category", "ui"),
                page=item.get("page", "1"),
                description=item.get("description", ""),
            )
        )

    return Plan(
        thinking=thinking,
        plan_description=plan_description,
        checklist=checklist,
    )


def plan_to_dict(plan: Plan) -> dict:
    """
    Convert Plan to dictionary for JSON response.

    Args:
        plan: Plan object

    Returns:
        Dictionary representation
    """
    return {
        "thinking": plan.thinking,
        "planDescription": plan.plan_description,
        "checklist": [
            {
                "id": item.id,
                "status": item.status,
                "category": item.category,
                "page": item.page,
                "description": item.description,
            }
            for item in plan.checklist
        ],
    }

"""
Build XML from image analyses.
"""

from typing import Any


def _escape_xml(text: str) -> str:
    """Escape special XML characters."""
    if not isinstance(text, str):
        text = str(text)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def build_analyses_to_xml(analyses: list[dict[str, Any]]) -> str:
    """
    Convert image analyses to XML format (like Libra's buildFilesToXml).

    Args:
        analyses: List of image analysis dictionaries

    Returns:
        XML string with <imageAnalyses> structure
    """
    image_xmls = []

    for i, analysis in enumerate(analyses, 1):
        page_ctx = analysis.get("pageContext", {})
        elements = analysis.get("uiElements", [])
        colors = analysis.get("colorPalette", [])
        typography = analysis.get("typography", {})
        layout = analysis.get("layout", "flex")
        flows = analysis.get("inferredFlows", [])

        # Build pageContext XML
        page_context_xml = f"""
    <pageContext>
      <name>{_escape_xml(page_ctx.get("name", f"Page {i}"))}</name>
      <purpose>{_escape_xml(page_ctx.get("purpose", ""))}</purpose>
      <region>{_escape_xml(page_ctx.get("region", "full_page"))}</region>
    </pageContext>"""

        # Build elements XML
        elements_xml = ""
        for elem in elements:
            pos = elem.get("position", {})
            styles = elem.get("styles", {})
            content = elem.get("content", {})

            elem_xml = f"""
      <element>
        <id>{_escape_xml(elem.get("id", ""))}</id>
        <type>{_escape_xml(elem.get("type", ""))}</type>
        <position x="{_escape_xml(pos.get("x", "0%"))}" 
                  y="{_escape_xml(pos.get("y", "0%"))}" 
                  width="{_escape_xml(pos.get("width", "0%"))}" 
                  height="{_escape_xml(pos.get("height", "0%"))}"/>
        <styles>
          <colors>{_escape_xml(",".join(styles.get("colors", [])))}</colors>
          <typography>{_escape_xml(styles.get("typography", ""))}</typography>
          <borderRadius>{_escape_xml(styles.get("borderRadius", "0"))}</borderRadius>
          <spacing>{_escape_xml(styles.get("spacing", ""))}</spacing>
          <shadow>{_escape_xml(styles.get("shadow", "none"))}</shadow>
        </styles>
        <content>
          <text>{_escape_xml(content.get("text", ""))}</text>
          <placeholder>{_escape_xml(content.get("placeholder", ""))}</placeholder>
          <alt>{_escape_xml(content.get("alt", ""))}</alt>
        </content>
        <state>{_escape_xml(elem.get("state", "default"))}</state>
        <interactions>{_escape_xml(elem.get("interactions", ""))}</interactions>
      </element>"""
            elements_xml += elem_xml

        # Build elements wrapper
        elements_wrapper = (
            f"""
    <uiElements>{elements_xml}
    </uiElements>"""
            if elements_xml
            else "\n    <uiElements/>"
        )

        # Build colors XML
        colors_xml = ""
        for color in colors:
            colors_xml += f"""
      <color hex="{_escape_xml(color.get("hex", ""))}" usage="{_escape_xml(color.get("usage", ""))}"/>"""

        colors_wrapper = (
            f"""
    <colorPalette>{colors_xml}
    </colorPalette>"""
            if colors_xml
            else "\n    <colorPalette/>"
        )

        # Build typography XML
        typography_xml = f"""
      <headings>{_escape_xml(",".join(typography.get("headings", [])))}</headings>
      <body>{_escape_xml(",".join(typography.get("body", [])))}</body>
      <sizes>{_escape_xml(",".join(typography.get("sizes", [])))}</sizes>"""

        typography_wrapper = f"""
    <typography>{typography_xml}
    </typography>"""

        # Build flows XML
        flows_xml = ""
        for flow in flows:
            flows_xml += f"""
      <flow>{_escape_xml(flow)}</flow>"""

        flows_wrapper = (
            f"""
    <inferredFlows>{flows_xml}
    </inferredFlows>"""
            if flows_xml
            else "\n    <inferredFlows/>"
        )

        # Build complete image XML
        image_xml = f"""  <image id="{i}">{page_context_xml}{elements_wrapper}{colors_wrapper}{typography_wrapper}
    <layout>{_escape_xml(layout)}</layout>{flows_wrapper}
  </image>"""

        image_xmls.append(image_xml)

    if not image_xmls:
        return "<imageAnalyses/>"

    return f"""<imageAnalyses>
{"".join(image_xmls)}
</imageAnalyses>"""


def build_user_prompt(
    analyses: list[dict[str, Any]], user_message: str | None = None
) -> str:
    """
    Build user prompt from analyses (like Libra's buildUserPrompt).

    Args:
        analyses: List of image analysis dictionaries
        user_message: Optional additional user message

    Returns:
        Complete user prompt string
    """
    xml_context = build_analyses_to_xml(analyses)

    user_request = ""
    if user_message:
        user_request = f"""
<userRequest>
{user_message}
</userRequest>"""

    return f"""Following below are the image analyses from video frames and the user request.

{xml_context}
{user_request}

Generate a detailed implementation plan in the specified XML format."""

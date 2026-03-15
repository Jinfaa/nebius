import { NextRequest, NextResponse } from "next/server";

export type ChatMessage = { role: "user" | "assistant"; content: string };

export async function POST(request: NextRequest) {
  const baseUrl = process.env.NEXT_PUBLIC_VIDEO2SITE_API_URL;
  if (!baseUrl) {
    return NextResponse.json(
      { error: "VIDEO2SITE_API_URL is not configured" },
      { status: 500 }
    );
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const messages = Array.isArray((body as { messages?: unknown }).messages)
    ? (body as { messages: ChatMessage[] }).messages
    : null;

  const plan = (body as { plan?: unknown }).plan;
  const xml = (body as { xml?: string }).xml ?? "";

  if (!messages || !messages.every(isValidMessage)) {
    return NextResponse.json(
      { error: "Body must contain 'messages' array of { role, content }" },
      { status: 400 }
    );
  }

  try {
    const cleanBaseUrl = baseUrl.replace(/\/$/, "");
    const res = await fetch(`${cleanBaseUrl}/generate-code-streaming`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages, plan, xml }),
    });

    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      return NextResponse.json(
        { error: data.error || "Generate code failed" },
        { status: res.status }
      );
    }

    return new Response(res.body, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      },
    });
  } catch (err) {
    const message =
      err instanceof Error ? err.message : "write-code request failed";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}

function isValidMessage(m: unknown): m is ChatMessage {
  return (
    typeof m === "object" &&
    m !== null &&
    "role" in m &&
    "content" in m &&
    (m as ChatMessage).role in { user: 1, assistant: 1 } &&
    typeof (m as ChatMessage).content === "string"
  );
}

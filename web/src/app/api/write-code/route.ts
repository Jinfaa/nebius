import { NextRequest, NextResponse } from "next/server";

export type ChatMessage = { role: "user" | "assistant"; content: string };

export async function POST(request: NextRequest) {
  const baseUrl = process.env.VIDEO2SITE_API_URL;
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
    return NextResponse.json(
      { error: "Invalid JSON body" },
      { status: 400 }
    );
  }

  const messages = Array.isArray((body as { messages?: unknown }).messages)
    ? (body as { messages: ChatMessage[] }).messages
    : null;

  if (!messages || !messages.every(isValidMessage)) {
    return NextResponse.json(
      { error: "Body must contain 'messages' array of { role, content }" },
      { status: 400 }
    );
  }

  try {
    const res = await fetch(`${baseUrl.replace(/\/$/, "")}/write-code`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages }),
    });

    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      return NextResponse.json(
        typeof data === "object" && data !== null && "error" in data
          ? data
          : { error: "write-code failed", details: data },
        { status: res.status }
      );
    }

    return NextResponse.json(data);
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

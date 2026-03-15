import { NextRequest, NextResponse } from "next/server";

export type ChatMessage = { role: "user" | "assistant"; content: string };

export async function POST(request: NextRequest) {
  const iframeDir = process.env.IFRAME_DIR!;

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const messages = Array.isArray((body as { messages?: unknown }).messages)
    ? (body as { messages: ChatMessage[] }).messages
    : null;

  if (!messages || !messages.every(isValidMessage)) {
    return NextResponse.json(
      { error: "Body must contain 'messages' array of { role, content }" },
      { status: 400 },
    );
  }

  try {
    return NextResponse.json({ success: true });
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

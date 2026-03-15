import { NextRequest, NextResponse } from "next/server";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ uploadId: string }> }
) {
  const baseUrl = process.env.NEXT_PUBLIC_VIDEO2SITE_API_URL;
  if (!baseUrl) {
    return NextResponse.json(
      { error: "VIDEO2SITE_API_URL is not configured" },
      { status: 500 }
    );
  }

  const { uploadId } = await params;

  try {
    const cleanBaseUrl = baseUrl.replace(/\/$/, "");
    const res = await fetch(`${cleanBaseUrl}/upload-progress/${uploadId}`, {
      method: "GET",
    });

    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      return NextResponse.json(
        { error: data.error || "Progress fetch failed" },
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
    const message = err instanceof Error ? err.message : "Request failed";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}

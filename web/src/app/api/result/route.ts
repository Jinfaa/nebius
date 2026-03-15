import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  const baseUrl = process.env.VIDEO2SITE_API_URL;
  if (!baseUrl) {
    return NextResponse.json(
      { error: "VIDEO2SITE_API_URL is not configured" },
      { status: 500 }
    );
  }

  const { searchParams } = new URL(request.url);
  const jobId = searchParams.get("jobId");

  const url = new URL("/result", baseUrl.replace(/\/$/, ""));
  if (jobId) url.searchParams.set("jobId", jobId);

  try {
    const res = await fetch(url.toString(), { method: "GET" });
    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      return NextResponse.json(
        typeof data === "object" && data !== null && "error" in data
          ? data
          : { error: "Result request failed", details: data },
        { status: res.status }
      );
    }

    return NextResponse.json(data);
  } catch (err) {
    const message =
      err instanceof Error ? err.message : "Result request failed";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}

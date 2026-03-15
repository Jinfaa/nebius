import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  const baseUrl = process.env.API_URL!;
  const { searchParams } = new URL(request.url);
  const openedAt = Number(searchParams.get("openedAt"));
  const url = new URL("/result", baseUrl.replace(/\/$/, ""));

  try {
    return NextResponse.json(
      Date.now() - openedAt < 2000
        ? {
            status: "pending",
            message: "Extracting frames... " + new Date(),
          }
        : {
            status: "finished",
            plan: "test " + Date.now(),
            imageUrls: ["/cat.jpg"],
          },
    );
  } catch (err) {
    const message =
      err instanceof Error ? err.message : "Result request failed";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}

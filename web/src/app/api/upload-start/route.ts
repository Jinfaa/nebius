import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest) {
  const baseUrl = process.env.NEXT_PUBLIC_VIDEO2SITE_API_URL;
  if (!baseUrl) {
    return NextResponse.json(
      { error: "VIDEO2SITE_API_URL is not configured" },
      { status: 500 }
    );
  }

  let formData: FormData;
  try {
    formData = await request.formData();
  } catch {
    return NextResponse.json(
      { error: "Invalid form data" },
      { status: 400 }
    );
  }

  const file = formData.get("file") ?? formData.get("input");

  if (!file || !(file instanceof File)) {
    return NextResponse.json(
      { error: "Missing file (use field 'file' or 'input')" },
      { status: 400 }
    );
  }

  const backendFormData = new FormData();
  backendFormData.append("file", file);

  try {
    const cleanBaseUrl = baseUrl.replace(/\/$/, "");
    const res = await fetch(`${cleanBaseUrl}/upload-start`, {
      method: "POST",
      body: backendFormData,
    });

    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      return NextResponse.json(
        { error: data.error || "Upload failed" },
        { status: res.status }
      );
    }

    return NextResponse.json(await res.json());
  } catch (err) {
    const message = err instanceof Error ? err.message : "Request failed";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}

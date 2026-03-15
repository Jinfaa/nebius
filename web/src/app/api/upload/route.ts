import { NextRequest, NextResponse } from "next/server";

const DEFAULT_OUTPUT = "./plan";

export async function POST(request: NextRequest) {
  const baseUrl = process.env.VIDEO2SITE_API_URL;
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
  const output = (formData.get("output") as string | null) ?? DEFAULT_OUTPUT;

  if (!file || !(file instanceof File)) {
    return NextResponse.json(
      { error: "Missing video file (use field 'file' or 'input')" },
      { status: 400 }
    );
  }

  const externalFormData = new FormData();
  externalFormData.append("input", file);
  externalFormData.append("output", output);

  try {
    return NextResponse.json({ success: true });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Upload request failed";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}

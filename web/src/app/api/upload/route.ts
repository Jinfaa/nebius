import { IFRAME_DIR, IFRAME_URL } from "@/helpers/constants";
import { startIframeDevServer, waitForPortReady } from "@/helpers/iframe-dev";
import { execSync } from "child_process";
import { existsSync, mkdirSync } from "fs";
import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest) {
  const iframeDir = IFRAME_DIR;
  const iframePort = IFRAME_URL.match(/:(\d+)/)?.[1]!;

  const formData = await request.formData();
  const file = formData.get("file") ?? formData.get("input");

  if (!file || !(file instanceof File)) {
    return NextResponse.json(
      { error: "Missing video file (use field 'file' or 'input')" },
      { status: 400 },
    );
  }


  const externalFormData = new FormData();
  externalFormData.append("input", file);
  externalFormData.append("dir", iframeDir);

  try {
    return NextResponse.json({ success: true });
  } catch (err) {
    const message =
      err instanceof Error ? err.message : "Upload request failed";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}

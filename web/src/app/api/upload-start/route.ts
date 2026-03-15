import { IFRAME_DIR, IFRAME_URL } from "@/helpers/constants";
import { startIframeDevServer, waitForPortReady } from "@/helpers/iframe-dev";
import { execSync } from "child_process";
import { existsSync, mkdirSync } from "fs";
import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest) {
  const baseUrl = process.env.NEXT_PUBLIC_VIDEO2SITE_API_URL;
  if (!baseUrl) {
    return NextResponse.json(
      { error: "VIDEO2SITE_API_URL is not configured" },
      { status: 500 },
    );
  }

  let formData: FormData;
  try {
    formData = await request.formData();
  } catch {
    return NextResponse.json({ error: "Invalid form data" }, { status: 400 });
  }

  const file = formData.get("file") ?? formData.get("input");

  if (!file || !(file instanceof File)) {
    return NextResponse.json(
      { error: "Missing file (use field 'file' or 'input')" },
      { status: 400 },
    );
  }

  const iframeDir = IFRAME_DIR;
  const iframePort = IFRAME_URL.match(/:(\d+)/)?.[1]!;

  if (!existsSync(iframeDir)) {
    mkdirSync(iframeDir, { recursive: true });
    execSync(
      `mkdir -p "${iframeDir}" && ` +
        `cd "${iframeDir}" && ` +
        `pnpm create next-app . --typescript --tailwind --app --src-dir --import-alias "@/*" --use-pnpm --yes`,
    );
    startIframeDevServer(iframeDir, iframePort);
    try {
      await waitForPortReady(iframePort);
    } catch (err) {
      const message =
        err instanceof Error
          ? err.message
          : "Iframe dev server failed to start";
      return NextResponse.json({ error: message }, { status: 502 });
    }
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
        { status: res.status },
      );
    }

    return NextResponse.json(await res.json());
  } catch (err) {
    const message = err instanceof Error ? err.message : "Request failed";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}

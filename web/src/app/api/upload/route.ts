import { startIframeDevServer, waitForPortReady } from "@/helpers/iframe-dev";
import { execSync } from "child_process";
import { existsSync, mkdirSync } from "fs";
import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest) {
  const iframeDir = process.env.IFRAME_DIR!;
  const iframePort = process.env.IFRAME_URL!.match(/:(\d+)/)?.[1];

  const formData = await request.formData();
  const file = formData.get("file") ?? formData.get("input");

  if (!file || !(file instanceof File)) {
    return NextResponse.json(
      { error: "Missing video file (use field 'file' or 'input')" },
      { status: 400 },
    );
  }

  if (!existsSync(iframeDir)) {
    mkdirSync(iframeDir, { recursive: true });
    execSync(
      `mkdir -p "${iframeDir}" && ` +
        `cd "${iframeDir}" && ` +
        `pnpm create next-app . --typescript --tailwind --app --src-dir --import-alias "@/*" --use-pnpm --yes`,
    );
    const port = iframePort ?? "3001";
    startIframeDevServer(iframeDir, port);
    try {
      await waitForPortReady(port);
    } catch (err) {
      const message =
        err instanceof Error
          ? err.message
          : "Iframe dev server failed to start";
      return NextResponse.json({ error: message }, { status: 502 });
    }
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

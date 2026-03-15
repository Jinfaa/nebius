import { spawn } from "child_process";
import { existsSync, readFileSync, writeFileSync } from "fs";
import path from "path";

const DEV_SERVER_PID_FILE = ".dev-server.pid";
const PORT_READY_INTERVAL_MS = 500;
const PORT_READY_TIMEOUT_MS = 60_000;

export async function waitForPortReady(port: string): Promise<void> {
  const baseUrl = `http://127.0.0.1:${port}`;
  const deadline = Date.now() + PORT_READY_TIMEOUT_MS;

  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${baseUrl}/`, { method: "GET" });
      if (res.ok || res.status < 500) return;
    } catch {
      // Server not ready yet
    }
    await new Promise((r) => setTimeout(r, PORT_READY_INTERVAL_MS));
    console.log(`Waiting for port ${port} to be ready...`);
  }

  throw new Error(
    `Iframe dev server on port ${port} did not become ready within ${PORT_READY_TIMEOUT_MS}ms`,
  );
}

export function startIframeDevServer(
  iframeDir: string,
  iframePort: string,
): void {
  const pidPath = path.join(iframeDir, DEV_SERVER_PID_FILE);

  if (existsSync(pidPath)) {
    try {
      const pid = parseInt(readFileSync(pidPath, "utf8").trim(), 10);
      if (!Number.isNaN(pid)) {
        process.kill(pid, "SIGTERM");
      }
    } catch {
      // Process may already be dead; ignore
    }
  }

  const child = spawn("pnpm", ["run", "dev", "--port", iframePort], {
    cwd: iframeDir,
    detached: true,
    stdio: "ignore",
  });
  child.unref();

  if (child.pid != null) {
    writeFileSync(pidPath, String(child.pid), "utf8");
  }
}

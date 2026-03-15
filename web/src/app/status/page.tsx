"use client";

import { useCallback, useEffect, useRef, useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";

type PendingResult = { status: "pending"; message: string };
type FinishedResult = {
  status: "finished";
  plan: string;
  imageUrls: string[];
};

type Result = PendingResult | FinishedResult;

function isFinished(r: Result): r is FinishedResult {
  return r.status === "finished";
}

function StatusContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [message, setMessage] = useState<string>("Analyzing your video…");
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const openedAt = useRef(new Date());

  const fetchResult = useCallback(async () => {
    const url = `/api/result?openedAt=${openedAt.current.getTime()}`;
    const res = await fetch(url);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      setError((data.error as string) || "Failed to fetch status");
      return null;
    }
    return data as Result;
  }, []);

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      const result = await fetchResult();
      if (cancelled || result === null) return;
      setError(null);
      if (isFinished(result)) {
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
        const params = new URLSearchParams();
        params.set("plan", result.plan);
        params.set("imageUrls", JSON.stringify(result.imageUrls));
        router.replace(`/chat?${params.toString()}`);
        return;
      }
      setMessage(result.message);
    };

    poll();
    intervalRef.current = setInterval(poll, 500);

    return () => {
      cancelled = true;
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [fetchResult, router]);

  return (
    <main className="flex min-h-dvh flex-col items-center justify-center p-8">
      {error ? (
        <div
          className="flex items-center gap-2 rounded-lg border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger"
          role="alert"
        >
          <svg
            className="h-4 w-4 shrink-0"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={2}
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z"
            />
          </svg>
          {error}
        </div>
      ) : (
        <div className="flex flex-col items-center gap-6">
          <div className="relative flex h-16 w-16 items-center justify-center">
            <div className="absolute inset-0 animate-spin rounded-full border-2 border-transparent border-t-primary" />
            <div className="absolute inset-2 animate-spin rounded-full border-2 border-transparent border-b-primary/40" style={{ animationDirection: "reverse", animationDuration: "1.5s" }} />
            <svg
              className="h-6 w-6 text-primary"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={1.5}
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="m15.75 10.5 4.72-4.72a.75.75 0 0 1 1.28.53v11.38a.75.75 0 0 1-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 0 0 2.25-2.25v-9a2.25 2.25 0 0 0-2.25-2.25h-9A2.25 2.25 0 0 0 2.25 7.5v9a2.25 2.25 0 0 0 2.25 2.25Z"
              />
            </svg>
          </div>
          <div className="text-center">
            <p className="text-lg font-medium text-text">{message}</p>
            <p className="mt-1 text-sm text-text-dim">
              This may take a moment
            </p>
          </div>
        </div>
      )}
    </main>
  );
}

export default function StatusPage() {
  return (
    <Suspense
      fallback={
        <main className="flex min-h-dvh items-center justify-center">
          <div className="flex flex-col items-center gap-4">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-transparent border-t-primary" />
            <p className="text-text-muted">Loading…</p>
          </div>
        </main>
      }
    >
      <StatusContent />
    </Suspense>
  );
}

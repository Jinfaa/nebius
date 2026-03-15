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
  const jobId = searchParams.get("jobId");
  const [message, setMessage] = useState<string>("Loading…");
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchResult = useCallback(async () => {
    const url = jobId
      ? `/api/result?jobId=${encodeURIComponent(jobId)}`
      : "/api/result";
    const res = await fetch(url);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      setError((data.error as string) || "Failed to fetch status");
      return null;
    }
    return data as Result;
  }, [jobId]);

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
        router.push(`/chat?${params.toString()}`);
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
    <main
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "2rem",
      }}
    >
      {error ? (
        <p style={{ color: "#c00" }} role="alert">
          {error}
        </p>
      ) : (
        <p>{message}</p>
      )}
    </main>
  );
}

export default function StatusPage() {
  return (
    <Suspense fallback={<main style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center" }}><p>Loading…</p></main>}>
      <StatusContent />
    </Suspense>
  );
}

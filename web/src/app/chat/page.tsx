"use client";

import { useCallback, useEffect, useRef, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import md5 from "md5";
import { IFRAME_URL } from "@/helpers/constants";

type ChecklistItem = {
  id: string;
  status: string;
  category: string;
  page: string;
  description: string;
};

type PlanData = {
  thinking: string;
  planDescription: string;
  checklist: ChecklistItem[];
};

type PageData = {
  id: string;
  filename: string;
};

type ChatMessage = {
  role: "user" | "assistant" | "thinking";
  content: string;
  type?: "file" | "command";
  path?: string;
};

const CHAT_STORAGE_PREFIX = "nebius-chat-messages";

function getCanonicalQueryString(searchParams: URLSearchParams): string {
  return Array.from(searchParams.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([k, v]) => `${k}=${v}`)
    .join("&");
}

function getStorageKey(searchParams: URLSearchParams): string {
  const qs = getCanonicalQueryString(searchParams);
  return qs ? `${CHAT_STORAGE_PREFIX}-${md5(qs)}` : CHAT_STORAGE_PREFIX;
}

function loadMessagesFromStorage(searchParams: URLSearchParams): ChatMessage[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(getStorageKey(searchParams));
    if (raw) return JSON.parse(raw) as ChatMessage[];
  } catch {
    // ignore
  }
  return [];
}

function saveMessagesToStorage(
  searchParams: URLSearchParams,
  messages: ChatMessage[],
) {
  try {
    localStorage.setItem(getStorageKey(searchParams), JSON.stringify(messages));
  } catch {
    // ignore
  }
}

function parseChatParams(searchParams: ReturnType<typeof useSearchParams>) {
  const planJson = searchParams.get("plan") ?? "{}";
  let plan: PlanData = { thinking: "", planDescription: "", checklist: [] };
  try {
    plan = JSON.parse(planJson) as PlanData;
  } catch { /* ignore */ }

  let pages: PageData[] = [];
  try {
    const raw = searchParams.get("pages");
    if (raw) pages = JSON.parse(raw) as PageData[];
  } catch { /* ignore */ }

  const xml = searchParams.get("xml") ?? "";
  const uploadId = searchParams.get("uploadId") ?? "";

  return { plan, pages, xml, uploadId };
}

function ChatContent() {
  const searchParams = useSearchParams();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [plan, setPlan] = useState<PlanData>({ thinking: "", planDescription: "", checklist: [] });
  const [pages, setPages] = useState<PageData[]>([]);
  const [xml, setXml] = useState("");
  const [isProcessing, setIsProcessing] = useState(false);
  const [processingProgress, setProcessingProgress] = useState("");
  const [processingPercent, setProcessingPercent] = useState(0);
  const [iframeUrl] = useState(IFRAME_URL);
  const historyRef = useRef<HTMLDivElement>(null);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const hasHydrated = useRef(false);
  const skipNextSave = useRef(true);

  const { uploadId } = parseChatParams(searchParams);
  const querySignature = getCanonicalQueryString(searchParams);

  useEffect(() => {
    const { plan: p, pages: pg, xml: x } = parseChatParams(searchParams);
    setPlan(p);
    setPages(pg);
    setXml(x);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [querySignature]);

  useEffect(() => {
    if (!uploadId) return;

    const currentUploadId = uploadId;
    setIsProcessing(true);
    setMessages([{ role: "assistant", content: "🎬 Starting video processing..." }]);

    let cancelled = false;
    const abortController = new AbortController();

    const connectToProgress = async () => {
      try {
        const backendUrl = (process.env.NEXT_PUBLIC_VIDEO2SITE_API_URL ?? "").replace(/\/$/, "");
        const res = await fetch(`${backendUrl}/upload-progress/${currentUploadId}`, {
          signal: abortController.signal,
        });
        if (cancelled || !res.ok) {
          if (!cancelled) {
            setMessages((prev) => [...prev, { role: "assistant", content: `Error: ${res.statusText}` }]);
            setIsProcessing(false);
          }
          return;
        }

        const reader = res.body?.getReader();
        const decoder = new TextDecoder();
        if (!reader) return;

        let currentStage = "";

        while (true) {
          if (cancelled) break;
          
          const { done, value } = await reader.read();
          if (done || cancelled) break;

          const chunk = decoder.decode(value);
          const lines = chunk.split("\n");

          for (const line of lines) {
            if (cancelled) break;
            
            if (line.startsWith("event: ")) {
              currentStage = line.replace("event: ", "");
              continue;
            }

            if (line.startsWith("data: ")) {
              const dataStr = line.replace("data: ", "");
              try {
                const data = JSON.parse(dataStr);

                if (data.message) {
                  setProcessingProgress(data.message);
                  setProcessingPercent(data.progress || 0);
                  setMessages((prev) => {
                    const last = prev[prev.length - 1];
                    if (last?.content === data.message) return prev;
                    return [...prev, { role: "assistant", content: data.message }];
                  });
                }

                if (data.content) {
                  setXml((prev) => prev + data.content);
                }

                if (currentStage === "error") {
                  setMessages((prev) => [...prev, { role: "assistant", content: `❌ Error: ${data.message || "Unknown error"}` }]);
                  setIsProcessing(false);
                }

                if (currentStage === "complete" || data.progress === 100) {
                  if (data.pages) {
                    const newPages = data.pages.map((p: { id: string; filename: string }) => ({
                      id: p.id,
                      filename: p.filename,
                    }));
                    setPages(newPages);
                  }
                  const completedPlan: PlanData = data.plan ?? { thinking: "", planDescription: "", checklist: [] };
                  const completedXml: string = data.xml ?? "";
                  if (data.plan) setPlan(completedPlan);
                  if (data.xml) setXml(completedXml);

                  const autoMessage: ChatMessage = { role: "user", content: "Implement the plan and create all necessary files." };
                  setMessages((prev) => [...prev, autoMessage, { role: "assistant", content: "🤖 Generating code..." }]);
                  setIsProcessing(false);
                  setSending(true);

                  const completedAnalyses: unknown[] = data.analyses ?? [];
                  streamCodeGeneration([autoMessage], completedPlan, completedXml, completedAnalyses)
                    .catch((err) => {
                      setMessages((prev) => [...prev, { role: "assistant", content: `❌ Code generation error: ${err?.message ?? err}` }]);
                    })
                    .finally(() => setSending(false));
                }
              } catch { /* ignore */ }
            }
          }
        }
      } catch {
        if (!cancelled) {
          setMessages((prev) => [...prev, { role: "assistant", content: "Connection error" }]);
          setIsProcessing(false);
        }
      }
    };

    connectToProgress();

    return () => {
      cancelled = true;
      abortController.abort();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [uploadId]);

  useEffect(() => {
    if (uploadId) return;

    if (!hasHydrated.current) hasHydrated.current = true;
    const stored = loadMessagesFromStorage(searchParams);
    const { plan: p } = parseChatParams(searchParams);
    if (stored.length > 0) {
      setMessages(stored);
    } else if (p.planDescription) {
      const planMessage =
        `# Implementation Plan\n\n${p.planDescription}\n\n` +
        `## Checklist\n` +
        p.checklist
          .map((item) => `- [${item.status === "done" ? "x" : " "}] [${item.category}] ${item.description}`)
          .join("\n");
      setMessages([{ role: "assistant", content: planMessage }]);
    } else {
      setMessages([]);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [querySignature]);

  useEffect(() => {
    if (skipNextSave.current) {
      skipNextSave.current = false;
      return;
    }
    saveMessagesToStorage(searchParams, messages);
  }, [querySignature, messages, searchParams]);

  useEffect(() => {
    if (!historyRef.current) return;
    historyRef.current.scrollTop = historyRef.current.scrollHeight;
  }, [messages]);

  const streamCodeGeneration = useCallback(async (
    chatMessages: ChatMessage[],
    planData: PlanData,
    xmlData: string,
    analyses?: unknown[],
  ) => {
    const backendUrl = (process.env.NEXT_PUBLIC_VIDEO2SITE_API_URL ?? "").replace(/\/$/, "");
    const res = await fetch(`${backendUrl}/generate-code-streaming`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: chatMessages, plan: planData, xml: xmlData, analyses }),
    });

    if (!res.ok) return;

    const reader = res.body?.getReader();
    const decoder = new TextDecoder();
    if (!reader) return;

    let currentEventType = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value);
      const lines = chunk.split("\n");

      for (const line of lines) {
        if (line.startsWith("event: ")) {
          currentEventType = line.replace("event: ", "").trim();
          continue;
        }
        if (!line.startsWith("data: ")) continue;

        try {
          const data = JSON.parse(line.replace("data: ", ""));

          if (currentEventType === "thinking" || currentEventType === "thinking_complete") {
            if (data.content) {
              setMessages((prev) => {
                const last = prev[prev.length - 1];
                if (last?.role === "thinking") {
                  return [...prev.slice(0, -1), { ...last, content: last.content + data.content }];
                }
                return [...prev, { role: "thinking", content: data.content }];
              });
            }
          } else if (currentEventType === "description" || currentEventType === "description_complete") {
            if (data.content) {
              setMessages((prev) => {
                const last = prev[prev.length - 1];
                if (last?.role === "assistant") {
                  return [...prev.slice(0, -1), { ...last, content: last.content + data.content }];
                }
                return [...prev, { role: "assistant", content: data.content }];
              });
            }
          } else if (currentEventType === "action") {
            setMessages((prev) => [...prev, {
              role: "assistant",
              content: data.description || "",
              type: data.type,
              path: data.path,
            }]);
            if (iframeRef.current) {
              iframeRef.current.src = iframeRef.current.src;
            }
          }
        } catch { /* ignore */ }
      }
    }
  }, [iframeRef]);

  const sendMessage = useCallback(async () => {
    const text = input.trim();
    if (!text || sending) return;
    const newMessage: ChatMessage = { role: "user", content: text };
    setMessages((prev) => [...prev, newMessage]);
    setInput("");
    setSending(true);
    const nextMessages = [...messages, newMessage];
    try {
      await streamCodeGeneration(nextMessages, plan, xml);
    } catch {
      // ignore
    } finally {
      setSending(false);
    }
  }, [input, messages, sending, plan, xml, streamCodeGeneration]);

  const completedCount = plan.checklist?.filter((i) => i.status === "done").length ?? 0;
  const totalCount = plan.checklist?.length ?? 0;
  const progress = totalCount > 0 ? Math.round((completedCount / totalCount) * 100) : 0;

  const imageUrls = pages.map((p) => `/api/images/${p.filename}`);

  return (
    <main className="flex h-dvh w-screen overflow-hidden bg-surface">
      {/* Chat sidebar */}
      <aside className="flex w-1/4 min-w-0 flex-col border-r border-border">
        <div className="flex h-12 items-center gap-2 border-b border-border px-4">
          <Link
            href="/"
            className="text-sm font-bold tracking-tight text-text transition-colors hover:text-primary"
          >
            Video<span className="text-primary">2</span>Site
          </Link>
          <span className="text-text-dim">/</span>
          <svg
            className="h-4 w-4 text-primary"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={2}
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 0 1 .865-.501 48.172 48.172 0 0 0 3.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0 0 12 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018Z"
            />
          </svg>
          <span className="text-sm font-semibold text-text">Chat</span>
        </div>

        <div
          ref={historyRef}
          className="flex-1 space-y-3 overflow-y-auto p-3"
        >
          {isProcessing && (
            <div className="mb-4 rounded-lg bg-primary/10 p-3">
              <div className="mb-2 font-semibold text-text">Processing Video</div>
              <div className="mb-2 text-sm text-text-muted">{processingProgress}</div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-border">
                <div
                  className="h-full rounded-full bg-primary transition-all duration-300"
                  style={{ width: `${processingPercent}%` }}
                />
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            <div
              key={i}
              className={`rounded-xl px-3.5 py-2.5 text-sm leading-relaxed whitespace-pre-wrap break-words ${
                m.role === "user"
                  ? "ml-4 bg-user-bubble text-text"
                  : "mr-4 bg-surface-raised text-text"
              }`}
            >
              <span
                className={`mb-1 block text-xs font-semibold ${
                  m.role === "user" ? "text-primary" : "text-accent"
                }`}
              >
                {m.role === "user" ? "You" : "Plan"}
              </span>
              {m.content}
              {m.path && (
                <div className="mt-1 text-xs text-text-muted">
                  📄 {m.path}
                </div>
              )}
            </div>
          ))}
          {sending && (
            <div className="mr-4 flex items-center gap-2 rounded-xl bg-surface-raised px-3.5 py-2.5 text-sm text-text-muted">
              <div className="flex gap-1">
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-text-dim" style={{ animationDelay: "0ms" }} />
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-text-dim" style={{ animationDelay: "150ms" }} />
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-text-dim" style={{ animationDelay: "300ms" }} />
              </div>
              Thinking…
            </div>
          )}
        </div>

        {/* Checklist */}
        {plan.checklist && plan.checklist.length > 0 && (
          <div className="border-t border-border p-3">
            <div className="mb-2 flex items-center justify-between text-xs font-semibold text-text">
              <span>Checklist ({completedCount}/{totalCount})</span>
              <span>{progress}%</span>
            </div>
            <div className="mb-2 h-1 w-full overflow-hidden rounded-full bg-border">
              <div
                className="h-full rounded-full bg-success transition-all duration-300"
                style={{ width: `${progress}%` }}
              />
            </div>
            <div className="max-h-32 space-y-1 overflow-y-auto text-xs text-text-muted">
              {plan.checklist.slice(0, 8).map((item) => (
                <div key={item.id} className="flex items-center gap-1.5">
                  <input
                    type="checkbox"
                    checked={item.status === "done"}
                    readOnly
                    className="h-3 w-3 rounded border-border"
                  />
                  <span className={item.status === "done" ? "line-through" : ""}>
                    [{item.category}] {item.description}
                  </span>
                </div>
              ))}
              {plan.checklist.length > 8 && (
                <div className="text-text-dim">+{plan.checklist.length - 8} more items</div>
              )}
            </div>
          </div>
        )}

        <div className="border-t border-border p-3">
          <div className="flex flex-col gap-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  sendMessage();
                }
              }}
              placeholder="Type a message…"
              rows={3}
              className="w-full resize-none rounded-xl border border-border bg-surface-raised px-3.5 py-2.5 text-sm text-text placeholder-text-dim outline-none transition-colors duration-150 focus:border-primary focus:ring-1 focus:ring-primary/50"
            />
            <button
              type="button"
              onClick={sendMessage}
              disabled={sending || !input.trim()}
              className="flex items-center justify-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-medium text-white transition-all duration-150 hover:bg-primary-hover active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-40 cursor-pointer"
            >
              <svg
                className="h-4 w-4"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={2}
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M6 12 3.269 3.125A59.769 59.769 0 0 1 21.485 12 59.768 59.768 0 0 1 3.27 20.875L5.999 12Zm0 0h7.5"
                />
              </svg>
              Send
            </button>
          </div>
        </div>
      </aside>

      {/* Screenshots sidebar */}
      <aside className="flex w-1/4 min-w-0 flex-col border-r border-border">
        <div className="flex h-12 items-center gap-2 border-b border-border px-4">
          <svg
            className="h-4 w-4 text-primary"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={2}
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="m2.25 15.75 5.159-5.159a2.25 2.25 0 0 1 3.182 0l5.159 5.159m-1.5-1.5 1.409-1.409a2.25 2.25 0 0 1 3.182 0l2.909 2.909M3.75 21h16.5A2.25 2.25 0 0 0 22.5 18.75V5.25a2.25 2.25 0 0 0-2.25-2.25H3.75A2.25 2.25 0 0 0 1.5 5.25v13.5A2.25 2.25 0 0 0 3.75 21Z"
            />
          </svg>
          <span className="text-sm font-semibold text-text">Screenshots</span>
          {imageUrls.length > 0 && (
            <span className="rounded-full bg-surface-overlay px-2 py-0.5 text-xs text-text-muted">
              {imageUrls.length}
            </span>
          )}
        </div>

        <div className="flex-1 space-y-2 overflow-y-auto p-3">
          {imageUrls.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-2 py-12 text-text-dim">
              <svg
                className="h-8 w-8"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={1}
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="m2.25 15.75 5.159-5.159a2.25 2.25 0 0 1 3.182 0l5.159 5.159m-1.5-1.5 1.409-1.409a2.25 2.25 0 0 1 3.182 0l2.909 2.909M3.75 21h16.5A2.25 2.25 0 0 0 22.5 18.75V5.25a2.25 2.25 0 0 0-2.25-2.25H3.75A2.25 2.25 0 0 0 1.5 5.25v13.5A2.25 2.25 0 0 0 3.75 21Z"
                />
              </svg>
              <span className="text-xs">No screenshots yet</span>
            </div>
          ) : (
            imageUrls.map((url, i) => (
              <div
                key={i}
                className="overflow-hidden rounded-lg border border-border transition-all duration-150 hover:border-primary/50"
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={url}
                  alt={`Screenshot ${i + 1}`}
                  className="block w-full"
                />
              </div>
            ))
          )}
        </div>
      </aside>

      {/* Preview iframe */}
      <section className="flex min-w-0 flex-1 flex-col">
        <div className="flex h-12 items-center gap-2 border-b border-border px-4">
          <svg
            className="h-4 w-4 text-primary"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={2}
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 21a9.004 9.004 0 0 0 8.716-6.747M12 21a9.004 9.004 0 0 1-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 0 1 7.843 4.582M12 3a8.997 8.997 0 0 0-7.843 4.582m15.686 0A11.953 11.953 0 0 1 12 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0 1 21 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0 1 12 16.5a17.92 17.92 0 0 1-8.716-2.247m0 0A9.015 9.015 0 0 1 3 12c0-1.605.42-3.113 1.157-4.418"
            />
          </svg>
          <span className="text-sm font-semibold text-text">Preview</span>
          <div className="ml-auto flex items-center gap-1.5 rounded-lg bg-surface-raised px-3 py-1.5">
            <div className="h-2 w-2 rounded-full bg-success" />
            <span className="font-mono text-xs text-text-muted">
              {iframeUrl}
            </span>
          </div>
        </div>
        <iframe
          ref={iframeRef}
          src={IFRAME_URL}
          title="Preview"
          className="min-h-0 flex-1 border-none bg-white"
        />
      </section>
    </main>
  );
}

export default function ChatPage() {
  return (
    <Suspense
      fallback={
        <div className="flex h-dvh items-center justify-center bg-surface">
          <div className="flex flex-col items-center gap-4">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-transparent border-t-primary" />
            <p className="text-text-muted">Loading…</p>
          </div>
        </div>
      }
    >
      <ChatContent />
    </Suspense>
  );
}

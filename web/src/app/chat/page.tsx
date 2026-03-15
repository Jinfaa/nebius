"use client";

import { useCallback, useEffect, useRef, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
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
  return [...searchParams.entries()]
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
                  if (data.plan) {
                    setPlan(data.plan);
                  }
                  if (data.xml) {
                    setXml(data.xml);
                  }
                  setMessages((prev) => [...prev, { role: "assistant", content: "✅ Processing complete! You can now chat to generate code." }]);
                  setIsProcessing(false);
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

  const sendMessage = useCallback(async () => {
    const text = input.trim();
    if (!text || sending) return;
    const newMessage: ChatMessage = { role: "user", content: text };
    setMessages((prev) => [...prev, newMessage]);
    setInput("");
    setSending(true);
    const nextMessages = [...messages, newMessage];
    try {
      const res = await fetch("/api/write-code", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: nextMessages,
          plan: plan,
          xml: xml
        }),
      });

      const reader = res.body?.getReader();
      const decoder = new TextDecoder();

      if (reader) {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunk = decoder.decode(value);
          const lines = chunk.split("\n");

          for (const line of lines) {
            if (line.startsWith("data: ")) {
              const dataStr = line.replace("data: ", "");
              try {
                const data = JSON.parse(dataStr);

                switch (data.type) {
                  case "thinking":
                  case "thinking_complete":
                    setMessages((prev) => {
                      const last = prev[prev.length - 1];
                      if (last?.role === "thinking") {
                        return [...prev.slice(0, -1), {
                          ...last,
                          content: last.content + (data.data?.content || ""),
                        }];
                      }
                      return [...prev, {
                        role: "thinking",
                        content: data.data?.content || "",
                      }];
                    });
                    break;
                  case "description":
                  case "description_complete":
                    setMessages((prev) => {
                      const last = prev[prev.length - 1];
                      if (last?.role === "assistant") {
                        return [...prev.slice(0, -1), {
                          ...last,
                          content: last.content + (data.data?.content || ""),
                        }];
                      }
                      return [...prev, {
                        role: "assistant",
                        content: data.data?.content || "",
                      }];
                    });
                    break;
                  case "action":
                    setMessages((prev) => [...prev, {
                      role: "assistant",
                      content: data.data?.description || "",
                      type: data.data?.type,
                      path: data.data?.path,
                    }]);
                    
                    // Refresh iframe
                    if (iframeRef.current) {
                      iframeRef.current.src = iframeRef.current.src;
                    }
                    break;
                  case "complete":
                    break;
                }
              } catch { /* ignore */ }
            }
          }
        }
      }
    } catch {
      // Optional: show error
    } finally {
      setSending(false);
    }
  }, [input, messages, sending, plan, xml]);

  const completedCount = plan.checklist?.filter((i) => i.status === "done").length ?? 0;
  const totalCount = plan.checklist?.length ?? 0;
  const progress = totalCount > 0 ? Math.round((completedCount / totalCount) * 100) : 0;

  return (
    <main
      style={{
        display: "flex",
        width: "100vw",
        height: "100vh",
        overflow: "hidden",
      }}
    >
      {/* Left: Chat + Input + Checklist */}
      <aside
        style={{
          width: "25%",
          minWidth: 0,
          display: "flex",
          flexDirection: "column",
          borderRight: "1px solid #ddd",
        }}
      >
        {/* Messages */}
        <div
          ref={historyRef}
          style={{
            flex: "0 0 60%",
            overflowY: "auto",
            padding: "0.75rem",
          }}
        >
          {isProcessing && (
            <div style={{ marginBottom: "1rem", padding: "0.75rem", backgroundColor: "#e3f2fd", borderRadius: "8px" }}>
              <div style={{ fontWeight: "bold", marginBottom: "0.5rem" }}>Processing Video</div>
              <div style={{ fontSize: "0.9rem", marginBottom: "0.5rem" }}>{processingProgress}</div>
              <div style={{ width: "100%", height: "6px", backgroundColor: "#ddd", borderRadius: "3px" }}>
                <div style={{ width: `${processingPercent}%`, height: "100%", backgroundColor: "#4CAF50", borderRadius: "3px", transition: "width 0.3s" }} />
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            <div
              key={i}
              style={{
                marginBottom: "0.75rem",
                padding: "0.5rem",
                borderRadius: "6px",
                backgroundColor:
                  m.role === "user" ? "#e3f2fd" : m.role === "thinking" ? "#fff3e0" : "transparent",
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
              }}
            >
              <strong>
                {m.role === "user" ? "You" : m.role === "thinking" ? "Thinking" : "Plan"}:{" "}
              </strong>
              {m.content}
              {m.path && (
                <div style={{ fontSize: "0.85rem", color: "#666", marginTop: "0.25rem" }}>
                  📄 {m.path}
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Checklist */}
        {plan.checklist && plan.checklist.length > 0 && (
          <div
            style={{
              flex: "0 0 20%",
              overflowY: "auto",
              padding: "0.5rem",
              borderTop: "1px solid #ddd",
              borderBottom: "1px solid #ddd",
            }}
          >
            <div style={{ fontWeight: "bold", marginBottom: "0.5rem", fontSize: "0.85rem" }}>
              Checklist ({completedCount}/{totalCount}) - {progress}%
            </div>
            <div
              style={{
                width: "100%",
                height: "4px",
                background: "#eee",
                marginBottom: "0.5rem",
              }}
            >
              <div
                style={{
                  width: `${progress}%`,
                  height: "100%",
                  background: "#4CAF50",
                  transition: "width 0.3s",
                }}
              />
            </div>
            {plan.checklist.slice(0, 8).map((item) => (
              <div
                key={item.id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "0.5rem",
                  fontSize: "0.75rem",
                  marginBottom: "0.25rem",
                }}
              >
                <input type="checkbox" checked={item.status === "done"} readOnly />
                <span
                  style={{
                    textDecoration: item.status === "done" ? "line-through" : "none",
                  }}
                >
                  [{item.category}] {item.description}
                </span>
              </div>
            ))}
            {plan.checklist.length > 8 && (
              <div style={{ fontSize: "0.7rem", color: "#666" }}>
                +{plan.checklist.length - 8} more items
              </div>
            )}
          </div>
        )}

        {/* Input */}
        <div
          style={{
            flex: "0 0 20%",
            display: "flex",
            flexDirection: "column",
            padding: "0.5rem",
          }}
        >
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
              }
            }}
            placeholder="Type a message..."
            rows={3}
            style={{
              width: "100%",
              resize: "none",
              marginBottom: "0.5rem",
              padding: "0.5rem",
            }}
          />
          <button
            type="button"
            onClick={sendMessage}
            disabled={sending || !input.trim()}
            style={{
              padding: "0.5rem 1rem",
              cursor: sending || !input.trim() ? "not-allowed" : "pointer",
              opacity: sending || !input.trim() ? 0.6 : 1,
            }}
          >
            {sending ? "Sending..." : "Send"}
          </button>
        </div>
      </aside>

      {/* Middle: Screenshots */}
      <aside
        style={{
          width: "25%",
          minWidth: 0,
          overflowY: "auto",
          borderRight: "1px solid #ddd",
          padding: "0.5rem",
        }}
      >
        {pages.map((page, i) => (
          <div key={i} style={{ marginBottom: "0.5rem" }}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={`/api/images/${page.filename}`}
              alt={`Screenshot ${i + 1}`}
              style={{
                width: "100%",
                height: "auto",
                display: "block",
                borderRadius: "4px",
              }}
            />
          </div>
        ))}
      </aside>

      {/* Right: Preview */}
      <section
        style={{
          width: "50%",
          minWidth: 0,
          height: "100%",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <input
          type="text"
          readOnly
          value={IFRAME_URL}
          aria-label="Current iframe URL"
          style={{
            width: "100%",
            boxSizing: "border-box",
            padding: "0.5rem 0.75rem",
            margin: 0,
            border: "1px solid #ddd",
            borderLeft: "none",
            borderRadius: 0,
            background: "#f5f5f5",
            fontFamily: "monospace",
            fontSize: "0.875rem",
          }}
        />
        <iframe
          ref={iframeRef}
          src={IFRAME_URL}
          title="Preview"
          style={{
            flex: 1,
            minHeight: 0,
            width: "100%",
            border: "none",
          }}
        />
      </section>
    </main>
  );
}

export default function ChatPage() {
  return (
    <Suspense fallback={<div style={{ padding: "2rem" }}>Loading...</div>}>
      <ChatContent />
    </Suspense>
  );
}

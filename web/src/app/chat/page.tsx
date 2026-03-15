"use client";

import { useCallback, useEffect, useRef, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import md5 from "md5";
import { IFRAME_URL } from "@/helpers/constants";

type Message = { role: "user" | "assistant"; content: string };

const CHAT_STORAGE_PREFIX = "nebius-chat-messages";

/** Build a canonical query string (sorted keys) so same params => same hash. */
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

function loadMessagesFromStorage(searchParams: URLSearchParams): Message[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(getStorageKey(searchParams));
    if (raw) return JSON.parse(raw) as Message[];
  } catch {
    // ignore
  }
  return [];
}

function saveMessagesToStorage(
  searchParams: URLSearchParams,
  messages: Message[],
) {
  try {
    localStorage.setItem(getStorageKey(searchParams), JSON.stringify(messages));
  } catch {
    // ignore
  }
}

function parseChatParams(searchParams: ReturnType<typeof useSearchParams>) {
  const plan = searchParams.get("plan") ?? "";
  let imageUrls: string[] = [];
  try {
    const raw = searchParams.get("imageUrls");
    if (raw) imageUrls = JSON.parse(raw) as string[];
  } catch {
    // ignore
  }
  return { plan, imageUrls };
}

function ChatContent() {
  const searchParams = useSearchParams();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [iframeUrl, setIframeUrl] = useState(IFRAME_URL);
  const historyRef = useRef<HTMLDivElement>(null);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const hasHydrated = useRef(false);
  const skipNextSave = useRef(true);

  const { plan, imageUrls } = parseChatParams(searchParams);
  const querySignature = getCanonicalQueryString(searchParams);

  // Load from localStorage after mount (avoids hydration error). Re-load when query params change.
  useEffect(() => {
    if (!hasHydrated.current) hasHydrated.current = true;
    const stored = loadMessagesFromStorage(searchParams);
    if (stored.length > 0) {
      setMessages(stored);
    } else if (plan) {
      setMessages([{ role: "assistant", content: plan }]);
    } else {
      setMessages([]);
    }
  }, [querySignature, plan, searchParams]);

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
    const newMessage: Message = { role: "user", content: text };
    setMessages((prev) => [...prev, newMessage]);
    setInput("");
    setSending(true);
    const nextMessages = [...messages, newMessage];
    try {
      await fetch("/api/write-code", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: nextMessages }),
      });
    } catch {
      // Optional: show error in UI
    } finally {
      setSending(false);
    }
  }, [input, messages, sending]);

  return (
    <main
      style={{
        display: "flex",
        width: "100vw",
        height: "100vh",
        overflow: "hidden",
      }}
    >
      {/* Left sidebar 1: chat */}
      <aside
        style={{
          width: "25%",
          minWidth: 0,
          display: "flex",
          flexDirection: "column",
          borderRight: "1px solid #ddd",
        }}
      >
        <div
          ref={historyRef}
          style={{
            flex: "0 0 75%",
            overflowY: "auto",
            padding: "0.75rem",
          }}
        >
          {messages.map((m, i) => (
            <div
              key={i}
              style={{
                marginBottom: "0.75rem",
                padding: "0.5rem",
                borderRadius: "6px",
                backgroundColor: m.role === "user" ? "#e3f2fd" : "transparent",
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
              }}
            >
              <strong>{m.role === "user" ? "You" : "Plan"}: </strong>
              {m.content}
            </div>
          ))}
        </div>
        <div
          style={{
            flex: "0 0 25%",
            display: "flex",
            flexDirection: "column",
            padding: "0.5rem",
            borderTop: "1px solid #ddd",
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
            placeholder="Type a message…"
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
            Send
          </button>
        </div>
      </aside>

      {/* Left sidebar 2: screenshots */}
      <aside
        style={{
          width: "25%",
          minWidth: 0,
          overflowY: "auto",
          borderRight: "1px solid #ddd",
          padding: "0.5rem",
        }}
      >
        {imageUrls.map((url, i) => (
          <div key={i} style={{ marginBottom: "0.5rem" }}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={url}
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

      {/* Main: iframe */}
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
          value={iframeUrl}
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
    <Suspense fallback={<div style={{ padding: "2rem" }}>Loading…</div>}>
      <ChatContent />
    </Suspense>
  );
}

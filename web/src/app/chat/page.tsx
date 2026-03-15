"use client";

import { useCallback, useEffect, useRef, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";

type Message = { role: "user" | "assistant"; content: string };

const IFRAME_SRC = "http://localhost:4000";

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
  const historyRef = useRef<HTMLDivElement>(null);
  const initialized = useRef(false);

  const { plan, imageUrls } = parseChatParams(searchParams);

  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;
    if (plan) {
      setMessages([{ role: "assistant", content: plan }]);
    }
  }, [plan]);

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
                backgroundColor:
                  m.role === "user" ? "#e3f2fd" : "transparent",
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
        }}
      >
        <iframe
          src={IFRAME_SRC}
          title="Preview"
          style={{
            width: "100%",
            height: "100%",
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

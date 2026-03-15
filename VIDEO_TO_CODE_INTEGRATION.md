# Video-to-Code Integration Plan

## Overview

This document describes how to integrate the video-to-code system with your frontend. The system uses SSE (Server-Sent Events) for real-time streaming of plan generation progress.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER UPLOADS VIDEO                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     FRONTEND: Upload Page (page.tsx)                       │
│  - User selects video/image file                                           │
│  - Shows progress bar with stage updates                                    │
│  - Receives SSE events from backend                                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                      POST /api/upload-stream (SSE)
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     BACKEND: FastAPI (port 8000)                           │
│                                                                             │
│  POST /upload-stream                                                       │
│  ├── Stage 1: extracting (10%) - Extract frames from video                │
│  ├── Stage 2: frames_ready (40%) - Pages extracted                        │
│  ├── Stage 3: analyzing (50%) - AI analyzes UI elements                 │
│  ├── Stage 4: analyzed (70%) - Analysis complete                         │
│  ├── Stage 5: generating (80%) - Plan generation starts                   │
│  ├── chunk events - Streaming plan XML                                     │
│  └── complete (100%) - Full plan with checklist                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                              Redirect to /chat
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     FRONTEND: Chat Page (chat/page.tsx)                    │
│                                                                             │
│  ┌─────────────┬──────────────────────┬─────────────────────────────┐      │
│  │   25%      │        50%          │           25%             │      │
│  │  CHAT       │    PREVIEW          │       SCREENSHOTS          │      │
│  │  MESSAGES   │    IFRAME           │       /                    │      │
│  │             │    (localhost:4000) │       CHECKLIST            │      │
│  │  - Plan     │                     │                           │      │
│  │  - User    │                     │                           │      │
│  │  - AI resp │                     │                           │      │
│  └─────────────┴──────────────────────┴─────────────────────────────┘      │
│                                                                             │
│  Chat receives messages via SSE from /api/write-code                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## SSE Event Format

### Progress Events (during upload)

```typescript
// event: progress
{
  "stage": "extracting" | "stitching" | "frames_ready" | "analyzing" | "analyzed" | "generating",
  "message": "Extracting frames from video...",
  "progress": 10,  // 0-100
  "pages": [{"id": "page_1", "filename": "page_001.png"}],  // optional
  "analyses": [...]  // optional
}

// event: chunk
{
  "content": "<plan>"  // XML chunk being generated
}

// event: complete
{
  "message": "Plan generated successfully",
  "progress": 100,
  "pages": [{"id": "page_1", "filename": "page_001.png"}],
  "analyses": [...],
  "plan": {
    "thinking": "...",
    "planDescription": "...",
    "checklist": [
      {"id": "nav_1", "status": "pending", "category": "ui", "page": "1", "description": "Navigation bar"}
    ]
  },
  "xml": "<plan>...</plan>"
}

// event: error
{
  "message": "Error description"
}
```

### Chat Message Events (during code generation)

```typescript
// event: thinking
{
  "type": "thinking",
  "data": { "content": "Analyzing the request..." }
}

// event: description  
{
  "type": "description",
  "data": { "content": "I will create a modern landing page..." }
}

// event: action
{
  "type": "action",
  "data": {
    "type": "file",
    "path": "./src/App.tsx",
    "description": "Create main App component",
    "modified": "full file content..."
  }
}

// event: complete
{
  "type": "complete",
  "data": { "success": true }
}
```

---

## Backend API (Already Implemented)

The backend provides the following endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/upload-stream` | POST | Upload video/image, receive SSE progress |
| `/health` | GET | Health check |

### Testing the Backend

```bash
# Start the backend
cd api
uv sync
uvicorn src.frame_extractor.main:app --port 8000 --host 0.0.0.0

# Test with an image (simpler than video)
curl -X POST -F "file=@test.png" http://localhost:8000/upload-stream

# Test with video
curl -X POST -F "file=@test.mp4" http://localhost:8000/upload-stream
```

---

## Frontend Integration Steps

### Step 1: Environment Configuration

Add to your frontend environment:

```bash
# web/.env.local
NEXT_PUBLIC_VIDEO2SITE_API_URL=http://localhost:8000
NEXT_PUBLIC_PREVIEW_URL=http://localhost:4000
```

### Step 2: Create Upload API Route

Create `web/src/app/api/upload-stream/route.ts`:

```typescript
import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest) {
  const baseUrl = process.env.NEXT_PUBLIC_VIDEO2SITE_API_URL;
  if (!baseUrl) {
    return NextResponse.json(
      { error: "VIDEO2SITE_API_URL is not configured" },
      { status: 500 }
    );
  }

  let formData: FormData;
  try {
    formData = await request.formData();
  } catch {
    return NextResponse.json(
      { error: "Invalid form data" },
      { status: 400 }
    );
  }

  const file = formData.get("file") ?? formData.get("input");

  if (!file || !(file instanceof File)) {
    return NextResponse.json(
      { error: "Missing file (use field 'file' or 'input')" },
      { status: 400 }
    );
  }

  const backendFormData = new FormData();
  backendFormData.append("file", file);

  try {
    const res = await fetch(`${baseUrl.replace(/\/$/, "")}/upload-stream`, {
      method: "POST",
      body: backendFormData,
    });

    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      return NextResponse.json(
        { error: data.error || "Upload failed" },
        { status: res.status }
      );
    }

    // Stream the response - IMPORTANT: pass through the SSE stream
    return new Response(res.body, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Request failed";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
```

### Step 3: Update Upload Page

Modify `web/src/app/page.tsx` to:

1. Accept video AND image files
2. Show progress during upload
3. Handle SSE stream
4. Redirect to chat with plan data

Key changes needed in `handleUpload`:

```typescript
const handleUpload = async () => {
  if (!file) return;
  
  setUploading(true);
  setError(null);
  setProgress("Starting upload...");

  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await fetch("/api/upload-stream", {
      method: "POST",
      body: formData,
    });

    if (!res.ok) {
      // handle error
      return;
    }

    // Read SSE stream
    const reader = res.body?.getReader();
    const decoder = new TextDecoder();
    
    let planData: PlanData | null = null;
    let pages: { id: string; filename: string }[] = [];
    let planXml = "";
    let currentStage = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value);
      const lines = chunk.split("\n");

      for (const line of lines) {
        if (line.startsWith("event: ")) {
          currentStage = line.replace("event: ", "");
          continue;
        }
        
        if (line.startsWith("data: ")) {
          const dataStr = line.replace("data: ", "");
          const data = JSON.parse(dataStr);

          // Update progress UI
          if (data.stage) {
            setProgress(data.message || "");
            setProgressPercent(data.progress || 0);
          }

          // Store data
          if (data.pages) pages = data.pages;
          if (data.content) planXml += data.content;
          if (data.plan) planData = data.plan;
          
          // On complete
          if (currentStage === "complete" || data.progress === 100) {
            if (data.pages) pages = data.pages;
            if (data.plan) planData = data.plan;
            if (data.xml) planXml = data.xml;
          }
        }
      }
    }

    // Navigate to chat
    if (planData) {
      const params = new URLSearchParams();
      params.set("plan", JSON.stringify(planData));
      params.set("pages", JSON.stringify(pages));
      params.set("xml", planXml);
      params.set("session", Date.now().toString());

      router.push(`/chat?${params.toString()}`);
    }
  } catch {
    // handle error
  } finally {
    setUploading(false);
  }
};
```

### Step 4: Update Chat Page

Modify `web/src/app/chat/page.tsx` to:

1. Parse plan, pages, and xml from URL params
2. Display initial plan as first message
3. Display checklist sidebar
4. Handle SSE from `/api/write-code` for code generation
5. Show preview iframe

#### Parse URL Parameters

```typescript
type PlanData = {
  thinking: string;
  planDescription: string;
  checklist: { id: string; status: string; category: string; page: string; description: string }[];
};

type PageData = { id: string; filename: string };

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

  return { plan, pages, xml };
}
```

#### Initialize with Plan Message

```typescript
useEffect(() => {
  if (initialized.current) return;
  initialized.current = true;
  
  if (plan.planDescription) {
    const planMessage = 
      `# Implementation Plan\n\n${plan.planDescription}\n\n` +
      `## Checklist\n` +
      plan.checklist
        .map(item => `- [${item.status === "done" ? "x" : " "}] [${item.category}] ${item.description}`)
        .join("\n");
    
    setMessages([{ role: "assistant", content: planMessage }]);
  }
}, [plan]);
```

#### Display Checklist Sidebar

```typescript
// Calculate progress
const completedCount = plan.checklist?.filter(i => i.status === "done").length ?? 0;
const totalCount = plan.checklist?.length ?? 0;
const progressPercent = totalCount > 0 ? Math.round((completedCount / totalCount) * 100) : 0;

// In render:
{plan.checklist && plan.checklist.length > 0 && (
  <div style={{ borderTop: "1px solid #ddd", padding: "0.5rem", maxHeight: "30%", overflowY: "auto" }}>
    <div style={{ fontWeight: "bold", marginBottom: "0.5rem" }}>
      Checklist ({completedCount}/{totalCount}) - {progressPercent}%
    </div>
    <div style={{ width: "100%", height: "4px", background: "#eee" }}>
      <div style={{ width: `${progressPercent}%`, height: "100%", background: "#4CAF50" }} />
    </div>
    {plan.checklist.map((item) => (
      <div key={item.id} style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.85rem" }}>
        <input type="checkbox" checked={item.status === "done"} readOnly />
        <span style={{ textDecoration: item.status === "done" ? "line-through" : "none" }}>
          [{item.category}] {item.description}
        </span>
      </div>
    ))}
  </div>
)}
```

#### Handle SSE for Code Generation

```typescript
const sendMessage = useCallback(async () => {
  const text = input.trim();
  if (!text || sending) return;
  
  const newMessage = { role: "user" as const, content: text };
  setMessages(prev => [...prev, newMessage]);
  setInput("");
  setSending(true);

  try {
    const res = await fetch("/api/write-code", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ 
        messages: [...messages, newMessage],
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
            const data = JSON.parse(dataStr);
            
            switch (data.type) {
              case "thinking":
              case "thinking_complete":
                // Add/update thinking message
                break;
              case "description":
              case "description_complete":
                // Add/update assistant message
                break;
              case "action":
                // Handle file/command actions
                // Update checklist based on action
                break;
              case "complete":
                // Finalize
                break;
            }
          }
        }
      }
    }
  } finally {
    setSending(false);
  }
}, [input, messages, plan, xml, sending]);
```

#### Layout Structure

```tsx
<main style={{ display: "flex", width: "100vw", height: "100vh", overflow: "hidden" }}>
  {/* Left: Chat + Input + Checklist */}
  <aside style={{ width: "25%", display: "flex", flexDirection: "column", borderRight: "1px solid #ddd" }}>
    <div ref={historyRef} style={{ flex: 1, overflowY: "auto", padding: "0.75rem" }}>
      {/* Messages */}
    </div>
    {/* Checklist */}
    <div style={{ borderTop: "1px solid #ddd", padding: "0.5rem", maxHeight: "30%", overflowY: "auto" }}>
      {/* Checklist items */}
    </div>
    {/* Input */}
    <div style={{ borderTop: "1px solid #ddd", padding: "0.5rem" }}>
      {/* Textarea + Send button */}
    </div>
  </aside>

  {/* Middle: Screenshots */}
  <aside style={{ width: "25%", overflowY: "auto", borderRight: "1px solid #ddd", padding: "0.5rem" }}>
    {pages.map((page, i) => (
      <img key={i} src={`/api/images/${page.filename}`} alt={`Screenshot ${i + 1}`} />
    ))}
  </aside>

  {/* Right: Preview */}
  <section style={{ width: "50%" }}>
    <iframe src={process.env.NEXT_PUBLIC_PREVIEW_URL} title="Preview" style={{ width: "100%", height: "100%", border: "none" }} />
  </section>
</main>
```

---

## Data Flow Diagram

```
1. USER UPLOAD
   └─► UploadPage uploads file via SSE
       └─► Backend /upload-stream
           ├─► Extract frames (video)
           ├─► Analyze with Vision AI
           ├─► Generate plan (streaming)
           └─► Return complete event with plan data

2. REDIRECT TO CHAT
   └─► /chat?plan=JSON&pages=JSON&xml=XML
       └─► Parse params, display initial plan

3. USER SENDS MESSAGE
   └─► ChatPage sends to /api/write-code
       └─► Backend generates code (SSE)
           ├─► thinking events
           ├─► description events  
           ├─► action events (file changes)
           └─► complete event

4. UPDATE CHECKLIST
   └─► Parse action events
       └─► Match to checklist items
       └─► Update status in UI
```

---

## Response Types

### Initial Plan Message

```markdown
# Implementation Plan

Generate a complete landing page web application based on the video mockups.

## Checklist
- [ ] [ui] Navigation bar with logo, menu, CTA
- [ ] [ui] Hero section with headline
- [ ] [dev] HTML structure
- [ ] [dev] Tailwind styling
```

### Thinking Message (during generation)

```markdown
Thinking: Analyzing the request to add a contact form...
```

### Action Message (code change)

```markdown
Action: Created src/components/ContactForm.tsx
```

---

## File Structure Summary

```
web/src/
├── app/
│   ├── page.tsx                    # Upload page - MODIFY
│   │                               
│   ├── chat/
│   │   └── page.tsx               # Chat page - MODIFY
│   │                               
│   └── api/
│       ├── upload-stream/
│       │   └── route.ts           # NEW - Proxy to backend
│       │                           
│       └── write-code/
│           └── route.ts            # EXISTING - Modify for SSE
```

---

## Environment Variables

```bash
# Backend (api/.env)
NEBIUS_API_KEY=your_nebius_api_key

# Frontend (web/.env.local)
NEXT_PUBLIC_VIDEO2SITE_API_URL=http://localhost:8000
NEXT_PUBLIC_PREVIEW_URL=http://localhost:4000
```

---

## Testing Checklist

- [ ] Backend running on port 8000
- [ ] Frontend running on port 3000
- [ ] Preview server running on port 4000
- [ ] Upload video → progress shows → redirect to chat
- [ ] Chat displays plan + checklist
- [ ] Screenshots visible in middle panel
- [ ] Preview iframe loads
- [ ] Send message → receives SSE chunks
- [ ] Checklist updates as code generates

---

## API Contract

### Upload Stream Request

```bash
POST /upload-stream
Content-Type: multipart/form-data

Parameters:
- file: File (video/* or image/*)
- user_message: string (optional)
```

### Upload Stream Response (SSE)

```
event: progress
data: {"stage": "...", "message": "...", "progress": 10, "pages": [...]}

event: progress  
data: {"stage": "...", "message": "...", "progress": 50, "analyses": [...]}

event: chunk
data: {"content": "<plan>..."}

event: complete
data: {"message": "...", "progress": 100, "pages": [...], "analyses": [...], "plan": {...}, "xml": "..."}
```

### Write Code Request

```bash
POST /api/write-code
Content-Type: application/json

{
  "messages": [...],
  "plan": {...},
  "xml": "..."
}
```

### Write Code Response (SSE)

```
event: thinking
data: {"type": "thinking", "data": {"content": "..."}}

event: description
data: {"type": "description", "data": {"content": "..."}}

event: action
data: {"type": "action", "data": {"type": "file", "path": "...", "description": "...", "modified": "..."}}

event: complete
data: {"type": "complete", "data": {"success": true}}
```

---

## Checklist Item Schema

```typescript
type ChecklistItem = {
  id: string;           // Unique identifier (e.g., "nav_1", "hero_1", "html")
  status: "pending" | "in_progress" | "done";
  category: "ui" | "dev" | "content";
  page: string;          // Page number (e.g., "1", "2")
  description: string;   // Human-readable description
};
```

---

## Complete Integration Example

### Frontend Upload Page

```tsx
// web/src/app/page.tsx
"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";

type PlanData = {
  thinking: string;
  planDescription: string;
  checklist: { 
    id: string; 
    status: string; 
    category: string; 
    page: string; 
    description: string 
  }[];
};

export default function UploadPage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState("");
  const [progressPercent, setProgressPercent] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const handleUpload = async () => {
    if (!file) return;
    
    setUploading(true);
    setError(null);
    setProgress("Starting...");
    setProgressPercent(0);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch("/api/upload-stream", {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setError(data.error || "Upload failed");
        setUploading(false);
        return;
      }

      const reader = res.body?.getReader();
      const decoder = new TextDecoder();
      
      if (!reader) {
        setError("Failed to read response");
        setUploading(false);
        return;
      }

      let planData: PlanData | null = null;
      let pages: { id: string; filename: string }[] = [];
      let planXml = "";
      let currentStage = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split("\n");

        for (const line of lines) {
          if (line.startsWith("event: ")) {
            currentStage = line.replace("event: ", "");
            continue;
          }
          
          if (line.startsWith("data: ")) {
            const dataStr = line.replace("data: ", "");
            try {
              const data = JSON.parse(dataStr);

              if (data.stage) {
                setProgress(data.message || "");
                setProgressPercent(data.progress || 0);
              }

              if (data.pages) pages = data.pages;
              if (data.content) planXml += data.content;
              if (data.plan) planData = data.plan;
              
              if (currentStage === "complete" || data.progress === 100) {
                if (data.pages) pages = data.pages;
                if (data.plan) planData = data.plan;
                if (data.xml) planXml = data.xml;
              }
            } catch {
              // Ignore parse errors
            }
          }
        }
      }

      if (planData) {
        const params = new URLSearchParams();
        params.set("plan", JSON.stringify(planData));
        params.set("pages", JSON.stringify(pages));
        params.set("xml", planXml);
        params.set("session", Date.now().toString());
        router.push(`/chat?${params.toString()}`);
      } else {
        setError("Failed to generate plan");
      }
    } catch {
      setError("Network error");
    } finally {
      setUploading(false);
    }
  };

  return (
    <main style={{ padding: "2rem" }}>
      <h1>Upload Video or Image</h1>
      
      <input
        type="file"
        accept="video/*,image/*"
        onChange={(e) => setFile(e.target.files?.[0] || null)}
      />
      
      {uploading && (
        <div style={{ marginTop: "1rem" }}>
          <p>{progress}</p>
          <div style={{ width: "100%", height: "8px", background: "#e0e0e0" }}>
            <div style={{ 
              width: `${progressPercent}%`, 
              height: "100%", 
              background: "#4CAF50",
              transition: "width 0.3s"
            }} />
          </div>
        </div>
      )}
      
      <button 
        onClick={handleUpload} 
        disabled={uploading || !file}
        style={{ marginTop: "1rem" }}
      >
        {uploading ? "Processing..." : "Upload & Generate"}
      </button>
      
      {error && <p style={{ color: "red" }}>{error}</p>}
    </main>
  );
}
```

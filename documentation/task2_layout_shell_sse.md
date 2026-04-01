# Task 2 — Layout shell, state machine & SSE consumer

## Context

ChatShop frontend is Next.js + TypeScript + Tailwind CSS, running on localhost:3000.
The backend FastAPI `/chat` endpoint streams typed SSE events (Task 1 complete):

```
{"type":"thinking", "message":"...", "detail":"..."}
{"type":"intent", "summary":"...", "semantic_query":"...", "filters":{...}}
{"type":"products", "items":[...]}
{"type":"response_chunk", "text":"..."}
{"type":"clarify"}
{"type":"done"}
{"type":"error", "message":"..."}
```

Currently the frontend has a basic scaffolded chatbox with no real layout or state logic.

## Goal

Build the layout shell, state machine, and SSE consumer. Product cards are NOT built in
this task — use a placeholder div. Chatbox continues to receive prose response as
streamed text, same as today. By end of this task:

- Layout transitions through all states driven by real backend events
- Orb + trace text render in top zone during thinking
- Intent chips render in top zone after planner fires
- Top zone shows a placeholder where cards will go
- Chatbox streams prose response as before
- Full mobile responsiveness baked in

---

## State machine

Define this in `frontend/src/lib/agentState.ts`:

```typescript
export type AgentState =
  | { status: "idle" }
  | { status: "thinking"; message: string; detail: string }
  | { status: "intent"; summary: string; semanticQuery: string; filters: Record<string, unknown> }
  | { status: "results"; items: ProductItem[] }
  | { status: "clarify" }

export interface ProductItem {
  product_id: string
  badge: string
  rationale: string
  key_attrs: string[]
  // raw product fields passed through
  name: string
  brand: string
  price: number
  type: string   // "over-ear" | "in-ear" | "on-ear"
  [key: string]: unknown
}
```

State transitions (one-way during a single turn):
```
idle → thinking → intent → thinking → results
idle → thinking → clarify
```

On new user message: always reset to `thinking` immediately, regardless of current state.
`results` and `clarify` persist until next user message.

---

## useAgentStream hook

Create `frontend/src/hooks/useAgentStream.ts`.

Responsibilities:
- POST to `/api/chat` (Next.js proxy to FastAPI) with `{ message, history }`
- Read the `ReadableStream` from the response body
- Parse SSE frames: split on `\n\n`, strip `data: ` prefix, `JSON.parse`
- Dispatch parsed events to update `AgentState`
- Accumulate `response_chunk` tokens into a `streamingText` string
- Call `onChunk(token)` callback so the chatbox can append tokens live
- Call `onDone()` when `type === "done"`
- Handle `type === "error"` gracefully

```typescript
interface UseAgentStreamOptions {
  onChunk: (token: string) => void
  onDone: () => void
}

export function useAgentStream(options: UseAgentStreamOptions) {
  const [agentState, setAgentState] = useState<AgentState>({ status: "idle" })

  const send = async (message: string, history: Message[]) => {
    setAgentState({ status: "thinking", message: "Decoding your request...", detail: "" })

    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, history }),
    })

    const reader = response.body!.getReader()
    const decoder = new TextDecoder()
    let buffer = ""

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const frames = buffer.split("\n\n")
      buffer = frames.pop() ?? ""

      for (const frame of frames) {
        if (!frame.startsWith("data: ")) continue
        try {
          const event = JSON.parse(frame.slice(6))
          dispatch(event, setAgentState, options)
        } catch {
          // malformed frame, skip
        }
      }
    }
  }

  return { agentState, send }
}
```

Dispatch logic:
```typescript
function dispatch(event: any, setState: ..., options: ...) {
  switch (event.type) {
    case "thinking":
      setState({ status: "thinking", message: event.message, detail: event.detail })
      break
    case "intent":
      setState({ status: "intent", summary: event.summary,
        semanticQuery: event.semantic_query, filters: event.filters })
      break
    case "products":
      setState({ status: "results", items: event.items })
      break
    case "clarify":
      setState({ status: "clarify" })
      break
    case "response_chunk":
      options.onChunk(event.text)
      break
    case "done":
      options.onDone()
      break
  }
}
```

---

## Layout shell

Create `frontend/src/components/ChatShopLayout.tsx`.

### Layout states

**idle** — centered chatbox:
```
┌─────────────────────────┐
│                         │
│   [hero text]           │
│   [chatbox input]       │
│   [suggestion pills]    │
│                         │
└─────────────────────────┘
```

**thinking / intent** — top zone appears, chatbox moves to bottom:
```
┌─────────────────────────┐
│  [top zone]             │  ~55% height
│  orb + status text      │
│  or intent chips        │
├─────────────────────────┤
│  [chat rail]            │  ~45% height
│  [input]                │
└─────────────────────────┘
```

**results** — top zone shows placeholder, chat rail below:
```
┌─────────────────────────┐
│  [top zone]             │  ~55% height
│  [PRODUCT CARDS HERE]   │  ← placeholder div for now
├─────────────────────────┤
│  [chat rail]            │
│  streaming text output  │
│  [input]                │
└─────────────────────────┘
```

**clarify** — no top zone, chatbox centered or bottom:
```
┌─────────────────────────┐
│                         │
│  [chat rail]            │
│  clarifying question    │
│  [input]                │
│                         │
└─────────────────────────┘
```

### CSS transitions

Use Tailwind transition classes on height and opacity. The top zone should:
- Not exist in DOM during `idle` and `clarify`
- Fade + slide in when entering `thinking`
- Stay visible through `intent` → `results`
- Dissolve immediately when user sends a new message (back to `thinking`)

Use `transition-all duration-300 ease-in-out` as the base. Avoid layout shifts on
the chat rail — pin it to the bottom with flexbox rather than animating its position.

### Top zone sub-components (inline in this task, no separate files needed)

**OrbSpinner** — three concentric rings, CSS animation, purple (`#534AB7` family).
Status text below: `message` in 14px/500, `detail` in 12px muted. Centered in zone.

**IntentPanel** — shown when `agentState.status === "intent"`:
- Card: "What I understood" → `summary`
- Card: "Searching for" → `semanticQuery` in monospace
- Card: "Filters" → chips for each filter key/value pair
- Subtle pulsing dots below indicating search in progress

**ProductsPlaceholder** — shown when `agentState.status === "results"`:
```tsx
<div className="flex gap-3 p-4">
  {agentState.items.map(item => (
    <div key={item.product_id} className="flex-1 border rounded-xl p-3 text-xs text-muted">
      <div className="font-medium">{item.name}</div>
      <div className="text-purple-500">{item.badge}</div>
      <div className="mt-1 opacity-60">{item.rationale}</div>
    </div>
  ))}
</div>
```
This gets replaced entirely in Task 3 — keep it throwaway simple.

---

## Mobile responsiveness

All layout states work identically on mobile. The only difference:

- Desktop: top zone cards lay out horizontally (flex-row, 3 columns)
- Mobile: top zone cards stack vertically (flex-col)

Use Tailwind responsive prefix: `flex-col md:flex-row` on the cards wrapper.

Top zone height on mobile: allow scroll within the zone (`overflow-y-auto`) rather
than fixed height, so 3 vertical cards don't overflow.

Chat rail on mobile: fixed to bottom, does not scroll off screen.

---

## Next.js API proxy

If not already present, add `frontend/src/app/api/chat/route.ts`:

```typescript
import { NextRequest } from "next/server"

export async function POST(req: NextRequest) {
  const body = await req.json()
  const upstream = await fetch("http://localhost:8000/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  return new Response(upstream.body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
    },
  })
}
```

---

## What NOT to build in this task

- Real product card components (Task 3)
- Chat message history rendering (Task 3)
- Suggestion pills interaction (can stub)
- Any backend changes

---

## Verification

1. Load the app — see centered chatbox, hero text, idle state
2. Type a message with enough detail (e.g. "waterproof running headphones under $150")
3. Top zone slides in, orb spins, status text cycles through thinking messages
4. Intent cards appear (summary, semantic query, filter chips)
5. Placeholder product cards appear in top zone with name + badge visible
6. Prose response streams into chatbox below
7. Type a follow-up — top zone dissolves immediately, orb reappears, cycle repeats
8. Test on narrow viewport — cards stack vertically, chat stays pinned to bottom

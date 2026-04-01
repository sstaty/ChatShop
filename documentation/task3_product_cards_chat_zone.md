# Task 3 — Product cards, chat zone redesign & contextual input

## Context

Task 2 is complete. We have:
- 4-state machine: `idle → thinking → intent → results / clarify`
- `useAgentStream` hook consuming typed SSE events
- Layout shell: top zone (intent chips → product placeholder) + bottom chat zone
- Mobile responsive: cards stack vertically on mobile

Task 3 replaces the throwaway placeholder components with real UI and redesigns
the chat zone interaction model. No backend changes.

---

## Change 1 — Orb moves into the chat zone

Currently the orb lives in the top zone. Move it to the bottom chat zone instead.

### New chat zone behaviour

The chat zone has three sub-states, driven by `agentState.status`:

**Input** (idle, results, clarify after response):
```
┌─────────────────────────────────┐
│  [latest assistant message]     │  ← single line or short paragraph
│  ─────────────────────────────  │
│  [text input]  [send]           │
└─────────────────────────────────┘
```

**Thinking** (status === "thinking" or "intent"):
```
┌─────────────────────────────────┐
│  [orb]  Decoding your vibe...   │
│         figuring out what you   │
│         actually want           │
└─────────────────────────────────┘
```
Input disappears entirely. Orb + status text fills the zone.
Orb is left-aligned, status text to its right (row layout).
On mobile: orb centered above text (column layout).

**Streaming** (response_chunk events arriving):
```
┌─────────────────────────────────┐
│  Found 3 that fit your brief.   │  ← streaming in token by token
└─────────────────────────────────┘
```
Orb dissolves, text streams in. No input yet.
Input reappears only when `type === "done"`.

Transition between sub-states: `transition-all duration-200 ease-in-out` on opacity.
Do not animate height — snap height, fade content.

### Top zone during thinking

While orb is in the chat zone, the top zone still shows intent chips when
`status === "intent"`. This is fine — two things happening simultaneously,
different zones. Top = information, bottom = interaction.

---

## Change 2 — Real product cards (replace placeholder)

Replace the `ProductsPlaceholder` div with a real `ProductCard` component.

This task stays frontend-only. The available item contract is still based on
`frontend/src/lib/agentState.ts`:

```typescript
interface ProductItem {
  product_id: string
  badge: string
  rationale: string
  key_attrs: string[]
  type?: "over-ear" | "in-ear" | "on-ear"
}
```

Implementation rules:
- use `product_id` as the displayed headphone name
- keep `badge`, `rationale`, and `key_attrs` as-is from the SSE payload
- support optional `type` on the frontend type for image selection when present
- if `type` is missing, infer it from `key_attrs` text or `product_id`; fall back to `over-ear`

### ProductCard component

Create `frontend/src/components/ProductCard.tsx`.

Props:
```typescript
interface ProductCardProps {
  name: string
  type: "over-ear" | "in-ear" | "on-ear"
  badge: string
  rationale: string
  keyAttrs: string[]
}
```

Layout (single card):
```
┌──────────────────────────────┐
│ [BADGE]                      │  ← colored top strip, full width
│                              │
│        [image]               │
│                              │
│  Type label                  │
│  Product name                │
│                              │
│  Rationale sentence here,    │
│  why this fits your needs.   │
│                              │
│  [chip] [chip] [chip]        │  ← key_attrs
└──────────────────────────────┘
```

### Badge colors

| Badge | Background | Text |
|-------|-----------|------|
| best match | `#534AB7` | `#EEEDFE` |
| best value | `#0F6E56` | `#E1F5EE` |
| luxury pick | `#3C3489` | `#CECBF6` |
| hidden gem | `#854F0B` | `#FAEEDA` |
| recommended | use `var(--color-background-secondary)` | `var(--color-text-secondary)` |

### Product images

Use the real images in `frontend/public/`:
- `over ear.jpg`
- `in ear.jpg`
- `on ear.jpg`

Select the image from `type`.

### Key attr chips

Small pill per item in `key_attrs`. Style:
```
font-size: 11px
padding: 3px 8px
border-radius: 20px
border: 0.5px solid var(--color-border-secondary)
color: var(--color-text-secondary)
background: var(--color-background-secondary)
```

### Cards layout in top zone

```tsx
<div className="flex justify-center gap-4 overflow-x-auto p-4">
  {items.map((item) => <ProductCard key={item.product_id} ... />)}
</div>
```

Layout rules:
- cards should read taller than they are wide
- show returned cards in a single horizontal row
- if 3 products arrive, render 3 cards side by side
- if 2 products arrive, center the 2 cards
- if 1 product arrives, center the 1 card
- on narrow screens, allow horizontal scrolling instead of collapsing the cards into very narrow columns

### Card entry animation

Cards should not all appear at once. Stagger them:
```typescript
// apply animation-delay per index
style={{ animationDelay: `${index * 80}ms` }}
```
Use a simple `fadeSlideUp` keyframe:
```css
@keyframes fadeSlideUp {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}
```

### Card dissolve on new message

When user sends a new message, the currently visible cards in the top zone should
fade out immediately (`opacity-0 transition-opacity duration-150`) before the top
zone transitions to intent chips. Do not wait for new results — dissolve on send.

---

## Change 3 — Contextual chatbox placeholder

The text input placeholder changes based on `agentState.status`:

```typescript
const placeholders: Record<string, string> = {
  idle:    "What are you shopping for?",
  results: "Want something cheaper? Different style?",
  clarify: "Tell me more...",
}
// default fallback:
const placeholder = placeholders[agentState.status] ?? "Ask me anything..."
```

Input is disabled (and hidden, replaced by orb) while `status === "thinking"` or
`status === "intent"`. Re-enable on `done`.

---

## Change 4 — Latest assistant message display

Above the input (when input is visible), show only the **latest assistant message**
— not full history.

```tsx
{latestMessage && (
  <div className="px-4 py-3 text-sm text-[var(--color-text-primary)] leading-relaxed border-b border-[var(--color-border-tertiary)]">
    {latestMessage}
  </div>
)}
```

`latestMessage` is a `string | null` in component state, set when:
- Streaming completes (`done` event fires) — set to the accumulated `streamingText`
- New user message sent — keep showing previous message until new one arrives

Do NOT show user messages in this zone. User message is implied by the orb appearing.
Full history is out of scope for this task.

---

## File structure for this task

```
frontend/src/components/
  ProductCard.tsx        ← new
  ChatZone.tsx           ← already extracted in Change 1
  OrbSpinner.tsx         ← already extracted in Change 1
```

Refactor `ChatShopLayout.tsx` to use these components. Keep the layout shell logic
(state machine wiring, top/bottom split) in `ChatShopLayout.tsx`.

---

## What NOT to change

- `useAgentStream` hook — no changes
- `useAgentStream` event handling — no changes
- Backend — no changes
- Full conversation history — out of scope, noted for future

---

## Verification

1. **Idle state**: centered chatbox, placeholder "What are you shopping for?", no top zone
2. **Send a detailed message**: input disappears, orb appears in chat zone with status text
3. **Intent fires**: intent chips appear in top zone, orb still spinning in chat zone
4. **Products arrive**: top zone transitions to product cards using `product_id` as the title and the mapped image by type, with staggered fade-in; orb dissolves and response streams as text in chat zone
5. **Done**: input reappears with placeholder "Want something cheaper? Different style?", latest assistant message shown above input
6. **Send follow-up**: cards dissolve immediately, orb reappears, cycle repeats
7. **Clarify path**: no cards, orb dissolves, clarifying question streams in, input reappears with "Tell me more..."
8. **Mobile** (narrow viewport): cards stay in a horizontal row and can scroll horizontally, orb + text go column layout, chat pinned to bottom

---

## Implementation notes

Implemented Change 1 in the frontend:
- extracted `OrbSpinner` into `frontend/src/components/OrbSpinner.tsx`
- extracted bottom-zone interaction rendering into `frontend/src/components/ChatZone.tsx`
- moved the orb out of the top zone; the top zone now only renders intent and results content
- replaced bottom full-history rendering with a 3-phase chat zone driven by local page state: waiting, streaming, and input
- added local `streamingText` and `latestAssistantMessage` handling in `page.tsx` without changing `useAgentStream` or `agentState.ts`

Deliberate deviation:
- the bottom waiting state keeps the orb visible until the first streamed token arrives, even if `results` or `clarify` events arrive earlier. This avoids flashing the input between SSE event phases and matches the intended interaction flow more closely than keying only off `agentState.status`.

Additional frontend polish completed:
- replaced the default font system with a display/body/mono pairing in `layout.tsx`
- added reusable surface, text, border, accent, and shadow tokens in `globals.css`
- increased assistant-output and latest-message typography for better readability
- restyled the shell, hero, suggestion pills, and chat input to use the shared visual system instead of ad hoc slate/sky utilities
- after visual review, simplified the palette back toward the original light sky direction and increased text/background contrast to avoid washed-out or unreadable surfaces
- refined the idle hero positioning so the landing-state chat sits lower and centered instead of clipping upward
- changed the accent toward a lighter cyan-blue and replaced the chat interior grey cast with a very light cyan surface gradient
- unified completed-response presentation with the streaming presentation so the answer stays visually consistent when the input returns
- corrected the idle chat container height to match the redesigned input row so the landing-state field no longer clips inside the panel
- removed the separate post-stream response layout; the response now renders in one persistent container from first token onward, with the input row simply appearing beneath it on completion
- tightened the landing-state vertical spacing so the hero copy and idle chatbox sit closer together again
- cleaned up repeated frontend utility strings by extracting reusable visual classes for badges, cards, chips, suggestion pills, input controls, chat shell, and response copy into `globals.css`

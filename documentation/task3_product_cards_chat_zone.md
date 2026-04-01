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

### ProductCard component

Create `frontend/src/components/ProductCard.tsx`.

Props:
```typescript
interface ProductCardProps {
  name: string
  brand: string
  price: number
  type: "over-ear" | "in-ear" | "on-ear"
  badge: string
  rationale: string
  key_attrs: string[]
}
```

Layout (single card):
```
┌──────────────────────────────┐
│ [BADGE]                      │  ← colored top strip, full width
│                              │
│  [SVG icon]  Brand           │
│              Name            │
│              $179            │
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

### SVG headphone icons

Inline SVG, no external assets. Three variants by `type`:

**over-ear:**
```svg
<svg width="40" height="40" viewBox="0 0 40 40" fill="none">
  <path d="M10 26v-8a10 10 0 0120 0v8" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
  <rect x="6" y="23" width="7" height="9" rx="3.5" fill="currentColor" opacity="0.7"/>
  <rect x="27" y="23" width="7" height="9" rx="3.5" fill="currentColor" opacity="0.7"/>
</svg>
```

**in-ear:**
```svg
<svg width="40" height="40" viewBox="0 0 40 40" fill="none">
  <circle cx="20" cy="24" r="7" stroke="currentColor" stroke-width="2"/>
  <circle cx="20" cy="24" r="3" fill="currentColor" opacity="0.5"/>
  <path d="M20 17V10" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
  <path d="M16 11.5L20 9l4 2.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
```

**on-ear:**
```svg
<svg width="40" height="40" viewBox="0 0 40 40" fill="none">
  <path d="M10 24v-6a10 10 0 0120 0v6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
  <rect x="6" y="21" width="8" height="8" rx="2" fill="currentColor" opacity="0.7"/>
  <rect x="26" y="21" width="8" height="8" rx="2" fill="currentColor" opacity="0.7"/>
  <path d="M14 20h12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
</svg>
```

Icon color: use the badge background color (or `#7F77DD` as neutral fallback).

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
<div className="flex flex-col md:flex-row gap-3 p-4 overflow-y-auto">
  {items.map(item => <ProductCard key={item.product_id} {...item} />)}
</div>
```

Mobile: `flex-col` — cards stack vertically, zone scrolls
Desktop: `flex-row` — 3 cards side by side, equal width (`flex: 1`)

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

When user sends a new message, cards in the top zone should fade out immediately
(`opacity-0 transition-opacity duration-150`) before the top zone transitions to
intent chips. Do not wait for new results — dissolve on send.

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
  ChatZone.tsx           ← new (extracts chat zone from ChatShopLayout)
  OrbSpinner.tsx         ← new (extracted from layout, now lives in chat zone)
```

Refactor `ChatShopLayout.tsx` to use these components. Keep the layout shell logic
(state machine wiring, top/bottom split) in `ChatShopLayout.tsx`.

---

## What NOT to change

- `useAgentStream` hook — no changes
- State machine types in `agentState.ts` — no changes
- Backend — no changes
- Full conversation history — out of scope, noted for future

---

## Verification

1. **Idle state**: centered chatbox, placeholder "What are you shopping for?", no top zone
2. **Send a detailed message**: input disappears, orb appears in chat zone with status text
3. **Intent fires**: intent chips appear in top zone, orb still spinning in chat zone
4. **Products arrive**: top zone transitions to 3 product cards (staggered fade-in), orb dissolves, response streams as text in chat zone
5. **Done**: input reappears with placeholder "Want something cheaper? Different style?", latest assistant message shown above input
6. **Send follow-up**: cards dissolve immediately, orb reappears, cycle repeats
7. **Clarify path**: no cards, orb dissolves, clarifying question streams in, input reappears with "Tell me more..."
8. **Mobile** (narrow viewport): cards stack vertically, orb + text go column layout, chat pinned to bottom

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

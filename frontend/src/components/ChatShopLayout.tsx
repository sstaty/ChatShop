"use client";

import { AgentState, ProductItem } from "@/lib/agentState";

const PILLS = ["running headphones", "for gym", "noise cancelling"];
const TOP_ZONE_VISIBLE = new Set(["thinking", "intent", "results"]);

// Approximate height of the input form only (p-3 + p-2 + input row)
const INPUT_HEIGHT = "80px";

// ---------------------------------------------------------------------------
// OrbSpinner
// ---------------------------------------------------------------------------

function OrbSpinner({ message, detail }: { message: string; detail: string }) {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-4">
      <div className="relative flex items-center justify-center w-20 h-20">
        {(
          [
            { size: 80, color: "#534AB7", duration: "1.2s", rev: false },
            { size: 56, color: "#7B74D4", duration: "0.9s", rev: true },
            { size: 32, color: "#A9A3E8", duration: "0.6s", rev: false },
          ] as const
        ).map(({ size, color, duration, rev }) => (
          <span
            key={size}
            className="absolute inline-block rounded-full border-2 border-transparent"
            style={{
              width: size,
              height: size,
              borderTopColor: color,
              animation: `orb-spin ${duration} linear infinite${rev ? " reverse" : ""}`,
            }}
          />
        ))}
      </div>
      <div className="text-center">
        <p className="text-sm font-medium text-slate-700">{message}</p>
        {detail && <p className="text-xs text-slate-400 mt-0.5">{detail}</p>}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// IntentPanel
// ---------------------------------------------------------------------------

function IntentPanel({
  summary,
  semanticQuery,
  filters,
}: {
  summary: string;
  semanticQuery: string;
  filters: Record<string, unknown>;
}) {
  const filterEntries = Object.entries(filters);
  return (
    <div className="flex flex-col gap-3 p-4 h-full overflow-y-auto">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div className="rounded-xl border border-slate-100 bg-slate-50 p-3">
          <p className="text-xs text-slate-400 mb-1">What I understood</p>
          <p className="text-sm text-slate-700">{summary}</p>
        </div>
        <div className="rounded-xl border border-slate-100 bg-slate-50 p-3">
          <p className="text-xs text-slate-400 mb-1">Searching for</p>
          <p className="text-sm font-mono text-slate-700 break-words">{semanticQuery}</p>
        </div>
        <div className="rounded-xl border border-slate-100 bg-slate-50 p-3">
          <p className="text-xs text-slate-400 mb-2">Filters</p>
          {filterEntries.length === 0 ? (
            <p className="text-xs text-slate-400 italic">none</p>
          ) : (
            <div className="flex flex-wrap gap-1">
              {filterEntries.map(([k, v]) => (
                <span key={k} className="rounded-full bg-purple-100 px-2 py-0.5 text-xs text-purple-700">
                  {k}: {String(v)}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
      <div className="flex items-center justify-center gap-1.5">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="inline-block w-1.5 h-1.5 rounded-full bg-purple-400"
            style={{ animation: `orb-pulse 1.2s ease-in-out ${i * 0.2}s infinite` }}
          />
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ProductsPlaceholder
// ---------------------------------------------------------------------------

function ProductsPlaceholder({ items }: { items: ProductItem[] }) {
  return (
    <div className="flex flex-col md:flex-row gap-3 p-4 overflow-y-auto h-full">
      {items.map((item) => (
        <div key={item.product_id} className="flex-1 rounded-xl border border-slate-100 bg-slate-50 p-3 text-xs">
          <div className="font-medium text-slate-700 truncate">{item.product_id}</div>
          <div className="text-purple-500 mt-0.5">{item.badge}</div>
          <div className="mt-1 text-slate-400 leading-relaxed line-clamp-3">{item.rationale}</div>
          {item.key_attrs.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {item.key_attrs.map((attr) => (
                <span key={attr} className="rounded-full bg-white border border-slate-200 px-2 py-0.5 text-slate-500">
                  {attr}
                </span>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function TopZoneContent({ agentState }: { agentState: AgentState }) {
  if (agentState.status === "thinking")
    return <OrbSpinner message={agentState.message} detail={agentState.detail} />;
  if (agentState.status === "intent")
    return <IntentPanel summary={agentState.summary} semanticQuery={agentState.semanticQuery} filters={agentState.filters} />;
  if (agentState.status === "results")
    return <ProductsPlaceholder items={agentState.items} />;
  return null;
}

// ---------------------------------------------------------------------------
// ChatShopLayout
// ---------------------------------------------------------------------------

interface ChatShopLayoutProps {
  agentState: AgentState;
  hasStarted: boolean;
  onPillClick: (text: string) => void;
  inputForm: React.ReactNode;
  messageRail: React.ReactNode;
  scrollRef: React.RefObject<HTMLDivElement | null>;
}

export function ChatShopLayout({
  agentState,
  hasStarted,
  onPillClick,
  inputForm,
  messageRail,
  scrollRef,
}: ChatShopLayoutProps) {
  const topVisible = TOP_ZONE_VISIBLE.has(agentState.status) && hasStarted;

  return (
    <main className="h-screen bg-sky-50 overflow-hidden relative">

      {/*
        ── Hero section ────────────────────────────────────────────────────
        Fills the space above the chatbox. Fades out on first send.
        `pointer-events: none` once fading so it can't block clicks.
      */}
      <div
        className="absolute inset-x-0 flex flex-col items-center justify-end px-4 text-center pb-8"
        style={{
          height: `calc(46vh - 16px)`,
          opacity: hasStarted ? 0 : 1,
          transition: "opacity 0.5s ease",
          pointerEvents: hasStarted ? "none" : "auto",
        }}
      >
        <h1 className="text-5xl font-bold text-slate-900 tracking-tight mb-3">ChatShop</h1>
        <p className="text-lg text-slate-600">
          Tell me what you need and I will find it.
          <br/>
          You don&apos;t have to browse categories or apply filters.
        </p>
        <p className="text-s text-slate-400 mt-3">Currently a headphones demo.</p>
      </div>

      {/*
        ── Brand name ──────────────────────────────────────────────────────
        Tiny label at top-center, fades in after first send.
      */}
      <div
        className="absolute top-3 inset-x-0 flex justify-center pointer-events-none"
        style={{
          opacity: hasStarted ? 1 : 0,
          transition: "opacity 0.5s ease 0.4s",
        }}
      >
        <span className="text-xs font-semibold text-slate-400 tracking-widest uppercase">
          ChatShop
        </span>
      </div>

      {/*
        ── Orb / top zone ──────────────────────────────────────────────────
        No background — orb floats freely. Fades in/out with opacity.
        Always rendered (so fade-out works); content switches via agentState.
      */}
      <div
        className="absolute inset-x-0 top-0 flex justify-center items-center px-4 md:px-8"
        style={{
          height: "calc(46vh - 16px)",
          opacity: topVisible ? 1 : 0,
          transition: "opacity 0.4s ease",
          pointerEvents: topVisible ? "auto" : "none",
        }}
      >
        <div className="w-full max-w-3xl h-full">
          <TopZoneContent agentState={agentState} />
        </div>
      </div>

      {/*
        ── Chatbox ─────────────────────────────────────────────────────────
        Always at top: 46vh. Height grows from input-only → full on first send.
        overflow-hidden clips the message rail during the grow animation.
      */}
      <div
        className="absolute inset-x-0 flex justify-center px-4 md:px-8"
        style={{
          top: "46vh",
          height: hasStarted ? "30vh" : INPUT_HEIGHT,
          transition: "height 1.4s cubic-bezier(0.4, 0, 0.2, 1)",
        }}
      >
        <div className="w-full max-w-3xl h-full rounded-3xl border border-sky-200 bg-white shadow-xl overflow-hidden flex flex-col">
          {/* Message rail — clipped during grow, scrollable once expanded */}
          <div
            ref={scrollRef}
            className="flex-1 min-h-0"
            style={{
              overflowY: hasStarted ? "auto" : "hidden",
              opacity: hasStarted ? 1 : 0,
              transition: "opacity 0.4s ease 0.8s",
            }}
          >
            {messageRail}
          </div>
          {/* Input form — always visible */}
          <div className={hasStarted ? "border-t border-slate-100 shrink-0" : "shrink-0"}>
            {inputForm}
          </div>
        </div>
      </div>

      {/*
        ── Suggestion pills ────────────────────────────────────────────────
        Below the chatbox. Fade out on first send.
      */}
      <div
        className="absolute inset-x-0 flex justify-center px-4 pt-10"
        style={{
          top: `calc(46vh + ${INPUT_HEIGHT} + 14px)`,
          opacity: hasStarted ? 0 : 1,
          transition: "opacity 0.4s ease",
          pointerEvents: hasStarted ? "none" : "auto",
        }}
      >
        <div className="flex flex-wrap gap-4 justify-center">
          {PILLS.map((pill) => (
            <button
              key={pill}
              onClick={() => onPillClick(pill)}
              className="rounded-full border border-sky-200 bg-white px-4 py-1.5 text-sm text-slate-600 hover:bg-sky-50 hover:border-sky-300 transition-colors shadow-sm"
            >
              {pill}
            </button>
          ))}
        </div>
      </div>

      <style>{`
        @keyframes orb-spin { to { transform: rotate(360deg); } }
        @keyframes orb-pulse {
          0%, 100% { opacity: 0.3; transform: scale(0.8); }
          50%       { opacity: 1;   transform: scale(1); }
        }
      `}</style>
    </main>
  );
}

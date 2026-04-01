"use client";

import { ChatZone } from "@/components/ChatZone";
import { ProductCard } from "./ProductCard";
import { AgentState, ProductItem, ProductVisualType } from "@/lib/agentState";

const PILLS = ["running headphones", "for gym", "noise cancelling"];
const TOP_ZONE_VISIBLE = new Set(["intent", "results"]);

// Approximate height of the input form only (p-3 + p-2 + input row)
const INPUT_HEIGHT = "108px";
const IDLE_CHAT_TOP = "58vh";
const STARTED_CHAT_TOP = "46vh";
const IDLE_CHAT_WIDTH = "max-w-2xl";
const STARTED_CHAT_WIDTH = "max-w-3xl";

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
    <div className="flex h-full flex-col gap-4 overflow-y-auto p-4 md:p-5">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <div className="rounded-[1.4rem] border border-[var(--color-border-secondary)] bg-[rgba(255,253,248,0.9)] p-4 shadow-[var(--shadow-soft)] backdrop-blur-sm">
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--color-text-tertiary)]">What I understood</p>
          <p className="text-[15px] leading-6 text-[var(--color-text-primary)]">{summary}</p>
        </div>
        <div className="rounded-[1.4rem] border border-[var(--color-border-secondary)] bg-[rgba(255,253,248,0.9)] p-4 shadow-[var(--shadow-soft)] backdrop-blur-sm">
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--color-text-tertiary)]">Searching for</p>
          <p className="font-mono text-[13px] leading-6 text-[var(--color-text-secondary)] wrap-break-word md:text-[13.5px]">{semanticQuery}</p>
        </div>
        <div className="rounded-[1.4rem] border border-[var(--color-border-secondary)] bg-[rgba(255,253,248,0.9)] p-4 shadow-[var(--shadow-soft)] backdrop-blur-sm">
          <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--color-text-tertiary)]">Filters</p>
          {filterEntries.length === 0 ? (
            <p className="text-[13px] italic text-[var(--color-text-tertiary)]">none</p>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {filterEntries.map(([k, v]) => (
                <span
                  key={k}
                  className="rounded-full border border-[var(--color-border-secondary)] bg-[var(--color-accent-soft)] px-2.5 py-1 text-[11px] font-medium text-[var(--color-accent-strong)]"
                >
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
            className="inline-block h-1.5 w-1.5 rounded-full bg-[var(--color-accent)]"
            style={{ animation: `orb-pulse 1.2s ease-in-out ${i * 0.2}s infinite` }}
          />
        ))}
      </div>
    </div>
  );
}

function inferProductType(item: ProductItem): ProductVisualType {
  if (item.type === "over-ear" || item.type === "in-ear" || item.type === "on-ear") {
    return item.type;
  }

  const haystack = [item.product_id, ...item.key_attrs]
    .join(" ")
    .toLowerCase();

  if (haystack.includes("in-ear") || haystack.includes("in ear") || haystack.includes("earbud")) {
    return "in-ear";
  }

  if (haystack.includes("on-ear") || haystack.includes("on ear")) {
    return "on-ear";
  }

  return "over-ear";
}

function ProductsPanel({
  items,
  isDismissing,
  renderVersion,
}: {
  items: ProductItem[];
  isDismissing: boolean;
  renderVersion: number;
}) {
  return (
    <div
      className={`flex h-full items-stretch justify-center gap-4 overflow-x-auto px-4 py-4 transition-opacity duration-150 md:px-5 ${
        isDismissing ? "opacity-0" : "opacity-100"
      }`}
    >
      {items.map((item, index) => (
        <div
          key={`${item.product_id}-${renderVersion}`}
          className="product-card-enter flex w-full max-w-[17rem] shrink-0 justify-center"
          style={{ animationDelay: `${index * 80}ms` }}
        >
          <ProductCard
            name={item.product_id}
            type={inferProductType(item)}
            badge={item.badge}
            rationale={item.rationale}
            keyAttrs={item.key_attrs}
          />
        </div>
      ))}
    </div>
  );
}

function TopZoneContent({
  agentState,
  visibleResults,
  isResultsDismissing,
  resultsRenderVersion,
}: {
  agentState: AgentState;
  visibleResults: ProductItem[];
  isResultsDismissing: boolean;
  resultsRenderVersion: number;
}) {
  if (visibleResults.length > 0) {
    return (
      <ProductsPanel
        items={visibleResults}
        isDismissing={isResultsDismissing}
        renderVersion={resultsRenderVersion}
      />
    );
  }

  if (agentState.status === "intent")
    return <IntentPanel summary={agentState.summary} semanticQuery={agentState.semanticQuery} filters={agentState.filters} />;

  return null;
}

// ---------------------------------------------------------------------------
// ChatShopLayout
// ---------------------------------------------------------------------------

interface ChatShopLayoutProps {
  agentState: AgentState;
  hasStarted: boolean;
  isAwaitingResponse: boolean;
  isStreaming: boolean;
  streamingText: string;
  latestAssistantMessage: string | null;
  visibleResults: ProductItem[];
  isResultsDismissing: boolean;
  resultsRenderVersion: number;
  onPillClick: (text: string) => void;
  inputForm: React.ReactNode;
}

export function ChatShopLayout({
  agentState,
  hasStarted,
  isAwaitingResponse,
  isStreaming,
  streamingText,
  latestAssistantMessage,
  visibleResults,
  isResultsDismissing,
  resultsRenderVersion,
  onPillClick,
  inputForm,
}: ChatShopLayoutProps) {
  const showingResults = visibleResults.length > 0;
  const topVisible = hasStarted && (showingResults || TOP_ZONE_VISIBLE.has(agentState.status));

  return (
    <main className="relative h-screen overflow-hidden bg-[var(--color-page)] text-[var(--color-text-primary)]">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(34,211,238,0.14),transparent_34%),radial-gradient(circle_at_82%_20%,rgba(255,255,255,0.62),transparent_20%)]" />

      {/*
        ── Hero section ────────────────────────────────────────────────────
        Fills the space above the chatbox. Fades out on first send.
        `pointer-events: none` once fading so it can't block clicks.
      */}
      <div
        className="absolute inset-x-0 flex flex-col items-center justify-end px-6 text-center md:px-8"
        style={{
          height: `calc(46vh - 16px)`,
          opacity: hasStarted ? 0 : 1,
          transition: "opacity 0.5s ease",
          pointerEvents: hasStarted ? "none" : "auto",
        }}
      >
        <div className="mb-3 rounded-full border border-[var(--color-border-primary)] bg-[rgba(255,255,255,0.82)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--color-accent-strong)] backdrop-blur-sm">
          Agent-led shopping interface
        </div>
        <h1 className="text-balance font-serif text-6xl font-semibold tracking-[-0.04em] text-[var(--color-text-primary)] sm:text-7xl md:text-[5.5rem]">
          ChatShop
        </h1>
        <p className="mt-4 max-w-2xl text-balance text-[17px] leading-8 text-[var(--color-text-secondary)] md:text-[19px]">
          Tell me what you need and I will find it.
          <br />
          You don&apos;t have to browse categories or apply filters.
        </p>
        <p className="mt-4 text-[13px] font-medium uppercase tracking-[0.16em] text-[var(--color-text-tertiary)]">
          Currently a headphones demo.
        </p>
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
        <span className="rounded-full border border-[var(--color-border-primary)] bg-[rgba(255,255,255,0.76)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--color-text-tertiary)] backdrop-blur-sm">
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
        <div className="h-full w-full max-w-5xl">
          <TopZoneContent
            agentState={agentState}
            visibleResults={visibleResults}
            isResultsDismissing={isResultsDismissing}
            resultsRenderVersion={resultsRenderVersion}
          />
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
          top: hasStarted ? STARTED_CHAT_TOP : IDLE_CHAT_TOP,
          height: hasStarted ? "32vh" : INPUT_HEIGHT,
          transform: hasStarted ? "none" : "translateY(-50%)",
          transition: "top 220ms ease, transform 220ms ease, height 220ms ease",
        }}
      >
        <div
          className={`flex h-full w-full flex-col overflow-hidden rounded-[2rem] border border-[var(--color-border-primary)] bg-[rgba(255,255,255,0.94)] shadow-[var(--shadow-panel)] backdrop-blur-md ${hasStarted ? STARTED_CHAT_WIDTH : IDLE_CHAT_WIDTH}`}
        >
          <ChatZone
            agentState={agentState}
            isAwaitingResponse={isAwaitingResponse}
            isStreaming={isStreaming}
            streamingText={streamingText}
            latestAssistantMessage={latestAssistantMessage}
            inputForm={inputForm}
          />
        </div>
      </div>

      {/*
        ── Suggestion pills ────────────────────────────────────────────────
        Below the chatbox. Fade out on first send.
      */}
      <div
        className="absolute inset-x-0 flex justify-center px-4 pt-8"
        style={{
          top: hasStarted ? `calc(${STARTED_CHAT_TOP} + ${INPUT_HEIGHT} + 14px)` : `calc(${IDLE_CHAT_TOP} + 52px)`,
          opacity: hasStarted ? 0 : 1,
          transition: "opacity 0.4s ease",
          pointerEvents: hasStarted ? "none" : "auto",
        }}
      >
        <div className="flex flex-wrap justify-center gap-3">
          {PILLS.map((pill) => (
            <button
              key={pill}
              onClick={() => onPillClick(pill)}
              className="rounded-full border border-[var(--color-border-primary)] bg-[rgba(255,255,255,0.92)] px-4 py-2 text-[13px] font-medium text-[var(--color-text-secondary)] shadow-[var(--shadow-soft)] transition-colors hover:border-[var(--color-accent)] hover:bg-[var(--color-accent-soft)] hover:text-[var(--color-accent-strong)]"
            >
              {pill}
            </button>
          ))}
        </div>
      </div>

      <style>{`
        @keyframes orb-pulse {
          0%, 100% { opacity: 0.3; transform: scale(0.8); }
          50% { opacity: 1; transform: scale(1); }
        }
      `}</style>
    </main>
  );
}

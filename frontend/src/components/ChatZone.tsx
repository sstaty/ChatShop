"use client";

import { useEffect, useRef, useState } from "react";
import { AgentState } from "@/lib/agentState";
import { OrbSpinner } from "@/components/OrbSpinner";

interface ChatZoneProps {
  agentState: AgentState;
  isAwaitingResponse: boolean;
  isStreaming: boolean;
  streamingText: string;
  latestAssistantMessage: string | null;
  inputForm: React.ReactNode;
}

const PRESET_POSITIONS: [number, number][] = [
  [18, 14], [14, 68], [24, 84], [70, 16], [74, 70],
  [80, 44], [10, 44], [58, 82], [42, 10], [84, 22],
];

// Fisher-Yates — actually random, unlike .sort(() => Math.random() - 0.5)
function fisherYates<T>(arr: T[]): T[] {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}


function extractIntentWords(semanticQuery: string, filters: Record<string, unknown>): string[] {
  const queryWords = semanticQuery.split(/\s+/).filter((w) => w.length > 2);
  const filterWords = Object.values(filters).map((v) => String(v)).filter((v) => v.length > 1);
  return [...new Set([...queryWords, ...filterWords])].slice(0, 3);
}

function getThinkingCopy(agentState: AgentState) {
  if (agentState.status === "thinking") return { message: agentState.message, detail: agentState.detail };
  if (agentState.status === "intent")   return { message: "Understanding your request...", detail: "Figuring out what you actually want" };
  if (agentState.status === "results")  return { message: "Lining up the best matches...", detail: "Turning results into a recommendation" };
  if (agentState.status === "clarify")  return { message: "Need one more detail...", detail: "Putting the follow-up question together" };
  return { message: "Working on it...", detail: "" };
}

type WordEntry = { word: string; pos: [number, number]; duration: number; delay: number };

export function ChatZone({
  agentState,
  isAwaitingResponse,
  isStreaming,
  streamingText,
  latestAssistantMessage,
  inputForm,
}: ChatZoneProps) {
  const showThinking = isAwaitingResponse && !isStreaming;
  const showInput = !isAwaitingResponse;
  const showResponseText = Boolean(streamingText || latestAssistantMessage);
  const responseText = streamingText || latestAssistantMessage || "";
  const reserveInputSpace = Boolean(isStreaming || showResponseText);
  const showIdleInput = showInput && !showResponseText;
  const thinkingCopy = getThinkingCopy(agentState);

  // mountId increments each time a new intent arrives — ensures fresh DOM elements
  // via key so animations always start from scratch, never restart mid-cycle
  const mountIdRef = useRef(0);
  const [mountId, setMountId] = useState(0);
  const [wordEntries, setWordEntries] = useState<WordEntry[]>([]);
  const clearTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const staggerTimersRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  const wordAnimationEnabled = false;

  useEffect(() => {
    if (!wordAnimationEnabled) return;
    if (agentState.status === "intent") {
      // Backend may emit multiple intent events per request (up to max_iterations=3).
      // Only start the stagger on the first intent; ignore subsequent ones while active.
      if (staggerTimersRef.current.length > 0) return;

      if (clearTimerRef.current) clearTimeout(clearTimerRef.current);

      mountIdRef.current += 1;
      const mid = mountIdRef.current;
      const words = extractIntentWords(agentState.semanticQuery, agentState.filters);
      const positions = fisherYates(PRESET_POSITIONS).slice(0, words.length);

      setMountId(mid);
      setWordEntries([]);

      words.forEach((word, i) => {
        const timer = setTimeout(() => {
          // Remove this timer from the active list so the guard resets after all words appear
          staggerTimersRef.current = staggerTimersRef.current.filter(t => t !== timer);
          setWordEntries(prev => [
            ...prev,
            {
              word,
              pos: positions[i],
              duration: 2,
              delay: 0,
            },
          ]);
        }, i * 1800);
        staggerTimersRef.current.push(timer);
      });
    } else if (agentState.status === "results" || agentState.status === "clarify") {
      staggerTimersRef.current.forEach(clearTimeout);
      staggerTimersRef.current = [];
      clearTimerRef.current = setTimeout(() => {
        setWordEntries([]);
        clearTimerRef.current = null;
      }, 300);
    }
  }, [agentState.status]);

  useEffect(() => () => {
    if (clearTimerRef.current) clearTimeout(clearTimerRef.current);
    staggerTimersRef.current.forEach(clearTimeout);
  }, []);

  return (
    <div className="relative h-full min-h-0 flex-1 overflow-hidden bg-[linear-gradient(180deg,#fbfeff_0%,var(--color-surface-muted)_100%)]">
      <div
        className={`absolute inset-0 flex items-center justify-center p-4 md:p-6 transition-all duration-200 ease-in-out ${
          showThinking ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
      >
        {wordEntries.map(({ word, pos, duration }) => (
          <span
            key={`${mountId}-${word}`}
            onAnimationIteration={() => {
              const newPos = PRESET_POSITIONS[Math.floor(Math.random() * PRESET_POSITIONS.length)];
              setWordEntries(prev =>
                prev.map(e => e.word === word ? { ...e, pos: newPos } : e)
              );
            }}
            style={{
              position: "absolute",
              top: `${pos[0]}%`,
              left: `${pos[1]}%`,
              animation: `word-float ${duration.toFixed(2)}s ease-in-out 0s infinite backwards`,
              fontSize: "16px",
              fontWeight: 600,
              letterSpacing: "0.04em",
              color: "var(--color-text-tertiary)",
              pointerEvents: "none",
              whiteSpace: "nowrap",
            }}
          >
            {word}
          </span>
        ))}

        <OrbSpinner message={thinkingCopy.message} detail={thinkingCopy.detail} />
      </div>

      <div
        className={`absolute inset-0 transition-all duration-200 ease-in-out ${
          showThinking ? "pointer-events-none opacity-0" : "opacity-100"
        }`}
      >
        {showIdleInput ? (
          <div className="flex h-full items-center justify-center px-3 py-3 md:px-4">
            <div className="w-full max-w-2xl">{inputForm}</div>
          </div>
        ) : (
          <div className="flex h-full flex-col justify-end">
            <div className="flex flex-1 items-center justify-center px-6 py-5 md:px-8 md:py-6">
              <div className="mx-auto flex w-full max-w-2xl items-center justify-center text-left">
                <p className="whitespace-pre-wrap text-[15px] leading-7 font-medium tracking-[-0.015em] text-[var(--color-text-primary)] md:text-[1.05rem] md:leading-8">
                  {responseText}
                </p>
              </div>
            </div>
            <div
              className={`transition-all duration-200 ease-in-out ${
                reserveInputSpace ? "border-t border-[var(--color-border-tertiary)]" : ""
              } ${showInput ? "bg-[rgba(255,255,255,0.55)] opacity-100" : "bg-transparent opacity-0"}`}
            >
              <div className={showInput ? "visible" : "invisible"}>{inputForm}</div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

"use client";

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

function getThinkingCopy(agentState: AgentState) {
  if (agentState.status === "thinking") {
    return { message: agentState.message, detail: agentState.detail };
  }

  if (agentState.status === "intent") {
    return {
      message: "Understanding your request...",
      detail: "Figuring out what you actually want",
    };
  }

  if (agentState.status === "results") {
    return {
      message: "Lining up the best matches...",
      detail: "Turning results into a recommendation",
    };
  }

  if (agentState.status === "clarify") {
    return {
      message: "Need one more detail...",
      detail: "Putting the follow-up question together",
    };
  }

  return { message: "Working on it...", detail: "" };
}

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

  return (
    <div className="relative h-full min-h-0 flex-1 overflow-hidden bg-[linear-gradient(180deg,#fbfeff_0%,var(--color-surface-muted)_100%)]">
      <div
        className={`absolute inset-0 flex items-center justify-center p-4 md:p-6 transition-all duration-200 ease-in-out ${
          showThinking ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
      >
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
                <p className="whitespace-pre-wrap text-[17px] leading-8 font-medium tracking-[-0.015em] text-[var(--color-text-primary)] md:text-[1.15rem] md:leading-9">
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
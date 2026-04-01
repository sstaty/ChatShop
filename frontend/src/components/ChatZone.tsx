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
  const showStreaming = isAwaitingResponse && isStreaming;
  const showInput = !isAwaitingResponse;
  const thinkingCopy = getThinkingCopy(agentState);

  return (
    <div className="relative h-full min-h-0 flex-1 overflow-hidden">
      <div
        className={`absolute inset-0 flex items-center justify-center p-4 md:p-6 transition-all duration-200 ease-in-out ${
          showThinking ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
      >
        <OrbSpinner message={thinkingCopy.message} detail={thinkingCopy.detail} />
      </div>

      <div
        className={`absolute inset-0 flex items-center p-4 md:p-6 transition-all duration-200 ease-in-out ${
          showStreaming ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
      >
        <p className="w-full whitespace-pre-wrap text-sm leading-relaxed text-slate-700">
          {streamingText}
        </p>
      </div>

      <div
        className={`absolute inset-0 flex flex-col justify-end transition-all duration-200 ease-in-out ${
          showInput ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
      >
        {latestAssistantMessage ? (
          <div className="border-b border-slate-100 px-4 py-3 text-sm leading-relaxed text-slate-700">
            {latestAssistantMessage}
          </div>
        ) : null}
        {inputForm}
      </div>
    </div>
  );
}
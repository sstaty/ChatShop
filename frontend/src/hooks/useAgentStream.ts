"use client";

import { useState } from "react";
import { AgentState, ProductItem } from "@/lib/agentState";

type Message = {
  role: "user" | "assistant";
  content: string;
};

interface UseAgentStreamOptions {
  onChunk: (token: string) => void;
  onDone: () => void;
  onError: (msg: string) => void;
  onProducts: (items: ProductItem[]) => void;
}

export function useAgentStream({ onChunk, onDone, onError, onProducts }: UseAgentStreamOptions) {
  const [agentState, setAgentState] = useState<AgentState>({ status: "idle" });

  const send = async (message: string, history: Message[], shownProducts: ProductItem[] = []) => {
    setAgentState({ status: "thinking", message: "Decoding your request...", detail: "" });

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, history, shown_products: shownProducts }),
      });

      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const frames = buffer.split("\n\n");
        buffer = frames.pop() ?? "";

        for (const frame of frames) {
          if (!frame.startsWith("data: ")) continue;
          try {
            const evt = JSON.parse(frame.slice(6));
            switch (evt.type) {
              case "thinking":
                setAgentState({ status: "thinking", message: evt.message, detail: evt.detail ?? "" });
                break;
              case "intent":
                setAgentState({
                  status: "intent",
                  summary: evt.summary,
                  semanticQuery: evt.semantic_query,
                  filters: evt.filters ?? {},
                });
                break;
              case "products":
                onProducts(evt.items ?? []);
                setAgentState({ status: "results", items: evt.items ?? [] });
                break;
              case "clarify":
                setAgentState({ status: "clarify" });
                break;
              case "response_chunk":
                onChunk(evt.text);
                break;
              case "done":
                setAgentState((prev) =>
                  prev.status === "results" ? prev : { status: "idle" }
                );
                onDone();
                break;
              case "error":
                onError(evt.message ?? "Unknown error");
                break;
            }
          } catch {
            // malformed frame, skip
          }
        }
      }
    } catch (err) {
      onError(err instanceof Error ? err.message : "Unknown error");
    }
  };

  return { agentState, send };
}

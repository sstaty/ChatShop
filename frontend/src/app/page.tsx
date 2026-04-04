"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { ChatShopLayout } from "@/components/ChatShopLayout";
import { useAgentStream } from "@/hooks/useAgentStream";
import { ProductItem } from "@/lib/agentState";

type Message = {
  role: "user" | "assistant";
  content: string;
};

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isAwaitingResponse, setIsAwaitingResponse] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingText, setStreamingText] = useState("");
  const [latestAssistantMessage, setLatestAssistantMessage] = useState<string | null>(null);
  const [hasStarted, setHasStarted] = useState(false);
  const [visibleResults, setVisibleResults] = useState<ProductItem[]>([]);
  const [isResultsDismissing, setIsResultsDismissing] = useState(false);
  const [resultsRenderVersion, setResultsRenderVersion] = useState(0);
  const streamingTextRef = useRef("");
  const isStreamingRef = useRef(false);
  const dismissTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (dismissTimerRef.current) {
        clearTimeout(dismissTimerRef.current);
      }
    };
  }, []);

  const { agentState, send } = useAgentStream({
    onChunk(token) {
      if (!isStreamingRef.current) {
        isStreamingRef.current = true;
        setIsStreaming(true);
      }
      streamingTextRef.current += token;
      setStreamingText(streamingTextRef.current);
    },
    onDone() {
      const completedMessage = streamingTextRef.current.trim();

      if (completedMessage) {
        setLatestAssistantMessage(completedMessage);
        setMessages((prev) => [...prev, { role: "assistant", content: completedMessage }]);
      }

      streamingTextRef.current = "";
      isStreamingRef.current = false;
      setStreamingText("");
      setIsStreaming(false);
      setIsAwaitingResponse(false);
    },
    onError(msg) {
      const errorMessage = `Error: ${msg}`;
      streamingTextRef.current = "";
      isStreamingRef.current = false;
      setStreamingText("");
      setIsStreaming(false);
      setIsAwaitingResponse(false);
      setLatestAssistantMessage(errorMessage);
      setMessages((prev) => [...prev, { role: "assistant", content: errorMessage }]);
    },
    onProducts(items) {
      if (dismissTimerRef.current) {
        clearTimeout(dismissTimerRef.current);
        dismissTimerRef.current = null;
      }

      setIsResultsDismissing(false);
      setVisibleResults(items);
      setResultsRenderVersion((prev) => prev + 1);
    },
  });

  const sendMessage = async (text: string) => {
    if (!text.trim() || isAwaitingResponse) return;

    const userMessage: Message = { role: "user", content: text };
    const nextMessages = [...messages, userMessage];

    setMessages(nextMessages);
    setHasStarted(true);
    setIsAwaitingResponse(true);
    setIsStreaming(false);
    setStreamingText("");

    streamingTextRef.current = "";
    isStreamingRef.current = false;
    await send(text, messages, visibleResults);
  };

  const handleSend = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = input.trim();
    if (!trimmed) return;
    setInput("");
    sendMessage(trimmed);
  };

  const placeholders: Record<string, string> = {
    idle: "What are you shopping for?",
    results: "Want something cheaper? Different style?",
    clarify: "Tell me more...",
  };

  const placeholder = placeholders[agentState.status] ?? "Ask me anything...";

  const inputForm = (
    <form onSubmit={handleSend} className="shrink-0 p-2 md:p-5">
      <div className="flex items-center gap-2 rounded-[1.4rem] border border-[var(--color-border-primary)] bg-[var(--color-surface)] p-1.5 shadow-[var(--shadow-soft)] md:gap-3 md:p-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={placeholder}
          disabled={isAwaitingResponse}
          className="w-full bg-transparent px-2.5 py-1 text-[14px] font-medium text-[var(--color-text-primary)] outline-none placeholder:text-[var(--color-text-tertiary)] md:px-3 md:py-2.5 md:text-[1rem]"
        />
        <button
          type="submit"
          disabled={isAwaitingResponse}
          className="shrink-0 rounded-[0.85rem] bg-[var(--color-accent)] px-4 py-1.5 text-[13px] font-semibold text-[var(--color-accent-contrast)] shadow-[0_10px_24px_rgba(34,211,238,0.24)] transition hover:bg-[var(--color-accent-strong)] disabled:cursor-not-allowed disabled:opacity-70 md:rounded-[1rem] md:px-5 md:py-3 md:text-[14px]"
        >
          Send
        </button>
      </div>
    </form>
  );

  return (
    <ChatShopLayout
      agentState={agentState}
      hasStarted={hasStarted}
      isAwaitingResponse={isAwaitingResponse}
      isStreaming={isStreaming}
      streamingText={streamingText}
      latestAssistantMessage={latestAssistantMessage}
      visibleResults={visibleResults}
      isResultsDismissing={isResultsDismissing}
      resultsRenderVersion={resultsRenderVersion}
      onPillClick={sendMessage}
      inputForm={inputForm}
    />
  );
}

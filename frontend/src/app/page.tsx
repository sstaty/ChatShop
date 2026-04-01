"use client";

import { FormEvent, useRef, useState } from "react";
import { ChatShopLayout } from "@/components/ChatShopLayout";
import { useAgentStream } from "@/hooks/useAgentStream";

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
  const streamingTextRef = useRef("");
  const isStreamingRef = useRef(false);

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
    await send(text, messages);
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
    <form onSubmit={handleSend} className="shrink-0 p-4 md:p-5">
      <div className="flex items-center gap-3 rounded-[1.4rem] border border-[var(--color-border-primary)] bg-[var(--color-surface)] p-2 shadow-[var(--shadow-soft)]">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={placeholder}
          disabled={isAwaitingResponse}
          className="w-full bg-transparent px-3 py-2.5 text-[15px] font-medium text-[var(--color-text-primary)] outline-none placeholder:text-[var(--color-text-tertiary)] md:text-[1rem]"
        />
        <button
          type="submit"
          disabled={isAwaitingResponse}
          className="shrink-0 rounded-[1rem] bg-[var(--color-accent)] px-5 py-3 text-[14px] font-semibold text-[var(--color-accent-contrast)] shadow-[0_10px_24px_rgba(34,211,238,0.24)] transition hover:bg-[var(--color-accent-strong)] disabled:cursor-not-allowed disabled:opacity-70"
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
      onPillClick={sendMessage}
      inputForm={inputForm}
    />
  );
}

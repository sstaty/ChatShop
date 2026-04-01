"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { ChatShopLayout } from "@/components/ChatShopLayout";
import { useAgentStream } from "@/hooks/useAgentStream";

type Message = {
  role: "user" | "assistant";
  content: string;
};

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [hasStarted, setHasStarted] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const streamingIndexRef = useRef<number | null>(null);
  const nextMessagesRef = useRef<Message[]>([]);

  const { agentState, send } = useAgentStream({
    onChunk(token) {
      if (streamingIndexRef.current === null) {
        streamingIndexRef.current = nextMessagesRef.current.length;
        setMessages([...nextMessagesRef.current, { role: "assistant", content: token }]);
      } else {
        const idx = streamingIndexRef.current;
        setMessages((prev) =>
          prev.map((msg, i) => (i === idx ? { ...msg, content: msg.content + token } : msg))
        );
      }
    },
    onDone() {
      streamingIndexRef.current = null;
      setIsSending(false);
    },
    onError(msg) {
      streamingIndexRef.current = null;
      setMessages((prev) => [...prev, { role: "assistant", content: `Error: ${msg}` }]);
      setIsSending(false);
    },
  });

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, agentState]);

  const sendMessage = async (text: string) => {
    if (!text.trim() || isSending) return;
    const userMessage: Message = { role: "user", content: text };
    const nextMessages = [...messages, userMessage];
    nextMessagesRef.current = nextMessages;
    streamingIndexRef.current = null;
    setMessages(nextMessages);
    setHasStarted(true);
    setIsSending(true);
    await send(text, messages);
  };

  const handleSend = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = input.trim();
    if (!trimmed) return;
    setInput("");
    sendMessage(trimmed);
  };

  const inputForm = (
    <form onSubmit={handleSend} className="p-3 shrink-0">
      <div className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-slate-50 p-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={hasStarted ? "Type your message..." : "What are you shopping for?"}
          disabled={isSending}
          className="w-full bg-transparent px-2 py-2 text-slate-800 outline-none placeholder:text-slate-400 text-sm"
        />
        <button
          type="submit"
          disabled={isSending}
          className="rounded-xl bg-sky-500 px-4 py-2 text-sm font-medium text-white transition hover:bg-sky-600 disabled:cursor-not-allowed disabled:opacity-70 shrink-0"
        >
          {isSending ? "Thinking..." : "Send"}
        </button>
      </div>
    </form>
  );

  const messageRail = (
    <div className="h-full px-4 py-3 space-y-3 flex flex-col">
      {messages.map((message, index) => (
        <div
          key={`${message.role}-${index}`}
          className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
        >
          <div
            className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
              message.role === "user"
                ? "bg-sky-500 text-white"
                : "bg-slate-100 text-slate-800"
            }`}
          >
            {message.content}
          </div>
        </div>
      ))}
    </div>
  );

  return (
    <ChatShopLayout
      agentState={agentState}
      hasStarted={hasStarted}
      onPillClick={sendMessage}
      inputForm={inputForm}
      messageRail={messageRail}
      scrollRef={scrollRef}
    />
  );
}

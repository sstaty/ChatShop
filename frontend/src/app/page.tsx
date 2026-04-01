"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

type Message = {
  role: "user" | "assistant";
  content: string;
};

function TracingIndicator({ text }: { text: string }) {
  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] rounded-2xl px-4 py-3 bg-white border border-slate-200 text-sm text-slate-500">
        <div className="flex items-center gap-2">
          <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-sky-500" />
          <span>{text || "Thinking..."}</span>
        </div>
      </div>
    </div>
  );
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [isTracing, setIsTracing] = useState(false);
  const [traceText, setTraceText] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isTracing]);

  const handleSend = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const trimmed = input.trim();
    if (!trimmed || isSending) {
      return;
    }

    const nextUserMessage: Message = { role: "user", content: trimmed };
    const nextMessages = [...messages, nextUserMessage];

    setMessages(nextMessages);
    setInput("");
    setIsSending(true);

    try {
      const response = await fetch("http://localhost:8000/chat/stream", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          message: trimmed,
          history: messages,
        }),
      });

      if (!response.ok) {
        throw new Error(`Request failed with status ${response.status}`);
      }

      setIsTracing(true);
      setTraceText("");

      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let streamingIndex: number | null = null;

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop()!;

          for (const line of lines) {
            if (!line.trim()) continue;
            let evt: { type: string; text: string };
            try {
              evt = JSON.parse(line);
            } catch {
              continue;
            }

            if (evt.type === "trace") {
              setTraceText(evt.text);
            } else if (evt.type === "token") {
              if (streamingIndex === null) {
                streamingIndex = nextMessages.length;
                setIsTracing(false);
                setTraceText("");
                setMessages([...nextMessages, { role: "assistant", content: evt.text }]);
              } else {
                setMessages((prev) =>
                  prev.map((msg, i) =>
                    i === streamingIndex
                      ? { ...msg, content: msg.content + evt.text }
                      : msg
                  )
                );
              }
            } else if (evt.type === "error") {
              setIsTracing(false);
              setTraceText("");
              setMessages((prev) => [
                ...prev,
                { role: "assistant", content: `Error: ${evt.text}` },
              ]);
            }
          }
        }
      } finally {
        reader.releaseLock();
      }
    } catch (error) {
      setIsTracing(false);
      setTraceText("");
      const errorMessage =
        error instanceof Error ? error.message : "Unknown error";
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `Error: ${errorMessage}` },
      ]);
    } finally {
      setIsSending(false);
    }
  };

  return (
    <main className="min-h-screen bg-sky-100 p-4 md:p-8">
      <section className="mx-auto flex h-[85vh] w-full max-w-3xl flex-col overflow-hidden rounded-3xl border border-sky-200 bg-white shadow-xl">
        <header className="border-b border-sky-100 px-6 py-4">
          <h1 className="text-xl font-semibold text-slate-800">ChatShop Assistant</h1>
        </header>

        <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto bg-slate-50 px-4 py-4 md:px-6">
          {messages.length === 0 && !isTracing ? (
            <p className="text-sm text-slate-500">Start the conversation by sending a message.</p>
          ) : (
            messages.map((message, index) => (
              <div
                key={`${message.role}-${index}`}
                className={`flex ${
                  message.role === "user" ? "justify-end" : "justify-start"
                }`}
              >
                <div
                  className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed md:text-base ${
                    message.role === "user"
                      ? "bg-sky-500 text-white"
                      : "bg-white text-slate-800 border border-slate-200"
                  }`}
                >
                  {message.content}
                </div>
              </div>
            ))
          )}
          {isTracing && <TracingIndicator text={traceText} />}
        </div>

        <form
          onSubmit={handleSend}
          className="border-t border-sky-100 bg-white p-3 md:p-4"
        >
          <div className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-slate-50 p-2">
            <input
              type="text"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="Type your message..."
              disabled={isSending}
              className="w-full bg-transparent px-2 py-2 text-slate-800 outline-none placeholder:text-slate-400"
            />
            <button
              type="submit"
              disabled={isSending}
              className="rounded-xl bg-sky-500 px-4 py-2 text-sm font-medium text-white transition hover:bg-sky-600 disabled:cursor-not-allowed disabled:opacity-70"
            >
              {isSending ? (isTracing ? "Thinking..." : "Sending...") : "Send"}
            </button>
          </div>
        </form>
      </section>
    </main>
  );
}

import { NextRequest } from "next/server";

export async function POST(req: NextRequest) {
  const body = await req.json();
  const upstream = await fetch(`${process.env.BACKEND_API_URL}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return new Response(upstream.body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
    },
  });
}

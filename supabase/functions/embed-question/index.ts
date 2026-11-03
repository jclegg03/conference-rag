import { corsHeaders, jsonResponse } from "../_shared/cors.ts";
import { getUser } from "../_shared/auth.ts";

// Turns a question into a 1,536-number vector using the same model as our stored sentences.
// The OpenAI key lives only here on the server (set with `supabase secrets set`).
Deno.serve(async (req) => {
  // Browsers send a preflight OPTIONS request before the real POST
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  if (req.method !== "POST") return jsonResponse({ error: "Method not allowed" }, 405);

  const user = await getUser(req);
  if (!user) return jsonResponse({ error: "You must be logged in" }, 401);

  let question: unknown;
  try {
    ({ question } = await req.json());
  } catch {
    return jsonResponse({ error: "Body must be JSON" }, 400);
  }
  if (typeof question !== "string" || !question.trim()) {
    return jsonResponse({ error: "Missing 'question'" }, 400);
  }

  const openaiRes = await fetch("https://api.openai.com/v1/embeddings", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${Deno.env.get("OPENAI_API_KEY")}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ model: "text-embedding-3-small", input: question.slice(0, 8000) }),
  });

  if (!openaiRes.ok) {
    console.error("OpenAI error", openaiRes.status, await openaiRes.text());
    return jsonResponse({ error: "Embedding service failed" }, 502);
  }

  const { data } = await openaiRes.json();
  return jsonResponse({ embedding: data[0].embedding });
});

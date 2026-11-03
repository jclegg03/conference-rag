import { corsHeaders, jsonResponse } from "../_shared/cors.ts";
import { getUser } from "../_shared/auth.ts";

// The "generation" half of RAG: the browser already retrieved the most relevant talks;
// here we hand them to GPT-4o as context and ask it to answer from them, with citations.

interface ContextTalk {
  title: string;
  speaker: string;
  text: string;
}

// Keeps a single huge talk from blowing up the prompt (and the bill)
const MAX_CHARS_PER_TALK = 20000;

const SYSTEM_PROMPT = `You answer questions using only the General Conference talks provided.
- Base every claim on the provided talks; do not add outside information.
- Cite talks inline by title and speaker, e.g. (“Title”, Speaker).
- If the talks don't address the question, say so plainly.
- Write plain text in a few short paragraphs. Do not use Markdown.`;

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  if (req.method !== "POST") return jsonResponse({ error: "Method not allowed" }, 405);

  const user = await getUser(req);
  if (!user) return jsonResponse({ error: "You must be logged in" }, 401);

  let question: unknown, context_talks: unknown;
  try {
    ({ question, context_talks } = await req.json());
  } catch {
    return jsonResponse({ error: "Body must be JSON" }, 400);
  }
  if (typeof question !== "string" || !question.trim()) {
    return jsonResponse({ error: "Missing 'question'" }, 400);
  }
  if (!Array.isArray(context_talks)) {
    return jsonResponse({ error: "'context_talks' must be an array" }, 400);
  }

  // The app's readiness check sends no talks; skip the paid OpenAI call
  if (context_talks.length === 0) {
    return jsonResponse({ answer: "No talks were provided, so there is nothing to answer from." });
  }

  const context = (context_talks as ContextTalk[])
    .map((t, i) => `[Talk ${i + 1}] “${t.title}” by ${t.speaker}\n${String(t.text ?? "").slice(0, MAX_CHARS_PER_TALK)}`)
    .join("\n\n---\n\n");

  const openaiRes = await fetch("https://api.openai.com/v1/chat/completions", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${Deno.env.get("OPENAI_API_KEY")}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: "gpt-4o",
      temperature: 0.3,
      messages: [
        { role: "system", content: SYSTEM_PROMPT },
        { role: "user", content: `Talks:\n\n${context}\n\nQuestion: ${question.slice(0, 2000)}` },
      ],
    }),
  });

  if (!openaiRes.ok) {
    console.error("OpenAI error", openaiRes.status, await openaiRes.text());
    return jsonResponse({ error: "Answer service failed" }, 502);
  }

  const data = await openaiRes.json();
  return jsonResponse({ answer: data.choices[0].message.content });
});

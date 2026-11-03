import { createClient } from "jsr:@supabase/supabase-js@2";

// We deploy with --no-verify-jwt, so each function checks the caller itself.
// Returns the logged-in user, or null if the request has no valid user session.
export async function getUser(req: Request) {
  const token = req.headers.get("Authorization")?.replace("Bearer ", "");
  if (!token) return null;

  const supabase = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_ANON_KEY")!,
  );
  // The anon key is also a valid JWT, but getUser() only succeeds for a real user session.
  const { data, error } = await supabase.auth.getUser(token);
  return error ? null : data.user;
}

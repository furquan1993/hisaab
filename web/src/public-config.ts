export function validatePublicConfig(url: string, key: string) {
  try {
    const parsed = new URL(url);
    const local = ["localhost", "127.0.0.1"].includes(parsed.hostname);
    if (
      (!local && parsed.protocol !== "https:") ||
      parsed.username ||
      parsed.password ||
      parsed.search ||
      parsed.hash ||
      parsed.pathname !== "/"
    )
      return false;
    if (key.startsWith("sb_publishable_")) return true;
    const claims = JSON.parse(
      atob(key.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")),
    );
    return claims.role === "anon";
  } catch {
    return false;
  }
}

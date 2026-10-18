import { randomBytes } from "node:crypto";
import { defineConfig, loadEnv } from "vite";
import { validatePublicConfig } from "./src/public-config.ts";

const noncePlaceholder = "HISAAB_DEVELOPMENT_NONCE";
// https://vite.dev/guide/env-and-mode#env-files
// https://vite.dev/guide/features#content-security-policy-csp
// https://vite.dev/guide/api-plugin#transformindexhtml
export default defineConfig(({ mode, command }) => {
  const env = loadEnv(mode, process.cwd());
  const url = env.VITE_SUPABASE_URL ?? "";
  const key = env.VITE_SUPABASE_PUBLISHABLE_KEY ?? "";
  if (key && !validatePublicConfig("https://configuration.supabase.co", key)) {
    throw Error("Private keys cannot be used in frontend configuration.");
  }
  const configured = validatePublicConfig(url, key);
  if (command === "build" && (url || key) && !configured) {
    throw Error("Use a project-root URL and public publishable/anon key only.");
  }
  const development = command === "serve";
  return {
    base: "/hisaab/",
    html: { cspNonce: development ? noncePlaceholder : undefined },
    plugins: [
      {
        name: "hisaab-exact-origin-csp",
        transformIndexHtml: {
          order: "post",
          handler(html) {
            // Fresh for each development HTML response, not a fixed deployed nonce.
            // Production contains no inline script/style and needs no nonce.
            const nonce = development ? randomBytes(24).toString("base64") : "";
            const nonceSource = development ? ` 'nonce-${nonce}'` : "";
            const connections = ["'self'"];
            if (configured) connections.push(new URL(url).origin);
            if (development)
              connections.push(
                "ws://127.0.0.1:5173",
                "ws://localhost:5173",
                "ws://127.0.0.1:5183",
              );
            const policy = [
              "default-src 'self'",
              `script-src 'self'${nonceSource}`,
              `style-src 'self'${nonceSource}`,
              `connect-src ${connections.join(" ")}`,
              "img-src 'self' data:",
              "object-src 'none'",
              "base-uri 'self'",
              "form-action 'none'",
            ].join("; ");
            return html
              .replace(
                "<!--HISAAB_CSP-->",
                `<meta http-equiv="Content-Security-Policy" content="${policy}"/>`,
              )
              .replaceAll(noncePlaceholder, nonce);
          },
        },
      },
    ],
  };
});

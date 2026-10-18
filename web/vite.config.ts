import { defineConfig, loadEnv } from "vite";
import { validatePublicConfig } from "./src/public-config.ts";

// Never emit an invalid/privileged key into an otherwise-disabled browser bundle.
// https://vite.dev/guide/env-and-mode#env-files
// https://vite.dev/guide/static-deploy#github-pages
export default defineConfig(({ mode, command }) => {
  const env = loadEnv(mode, process.cwd());
  const url = env.VITE_SUPABASE_URL ?? "",
    key = env.VITE_SUPABASE_PUBLISHABLE_KEY ?? "";
  if (key && !validatePublicConfig("https://configuration.supabase.co", key)) {
    throw Error("Private keys cannot be used in frontend configuration.");
  }
  if (command === "build" && (url || key) && !validatePublicConfig(url, key)) {
    throw Error(
      "Use a valid project URL and public publishable/anon key only. Private keys cannot be bundled.",
    );
  }
  return { base: "/hisaab/" };
});

import { describe, expect, it } from "vitest";
import { validatePublicConfig } from "./public-config";
describe("public-only frontend configuration", () => {
  it("accepts publishable keys over HTTPS and isolated loopback development", () => {
    expect(
      validatePublicConfig(
        "https://project.supabase.co",
        "sb_publishable_example",
      ),
    ).toBe(true);
    expect(
      validatePublicConfig("http://127.0.0.1:54321", "sb_publishable_example"),
    ).toBe(true);
  });
  it("rejects privileged keys, insecure remote hosts and credential-bearing URLs", () => {
    expect(
      validatePublicConfig("https://project.supabase.co", "sb_secret_example"),
    ).toBe(false);
    expect(
      validatePublicConfig(
        "http://project.supabase.co",
        "sb_publishable_example",
      ),
    ).toBe(false);
    expect(
      validatePublicConfig(
        "https://user:password@project.supabase.co",
        "sb_publishable_example",
      ),
    ).toBe(false);
    expect(
      validatePublicConfig(
        "postgresql://user:password@host/db",
        "sb_publishable_example",
      ),
    ).toBe(false);
  });
});

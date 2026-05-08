import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";

const webRoot = path.resolve(__dirname, "..", "..", "..");

function readProjectFile(relativePath: string): string {
  return readFileSync(path.join(webRoot, relativePath), "utf8");
}

test("root layout does not mount legacy AuthProvider", () => {
  const layout = readProjectFile("app/layout.tsx");
  assert.doesNotMatch(layout, /AuthProvider/);
  assert.doesNotMatch(layout, /context\/AuthContext/);
});

test("auth gate uses the current status endpoint instead of legacy /me", () => {
  const gate = readProjectFile("components/auth/AuthGate.tsx");
  assert.match(gate, /fetchAuthStatus/);
  assert.doesNotMatch(gate, /useAuth/);
  assert.doesNotMatch(gate, /AuthContext/);

  const authClient = readProjectFile("lib/auth.ts");
  assert.doesNotMatch(authClient, /\/api\/v1\/auth\/me/);
});

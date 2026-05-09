import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
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

test("authenticated shell exposes account navigation", () => {
  assert.ok(
    existsSync(path.join(webRoot, "app/(utility)/account/page.tsx")),
    "account page route should exist",
  );

  const accountLink = readProjectFile("components/auth/AccountLink.tsx");
  assert.match(accountLink, /fetchAuthStatus/);
  assert.match(accountLink, /href="\/account"/);

  const workspaceSidebar = readProjectFile("components/sidebar/WorkspaceSidebar.tsx");
  assert.match(workspaceSidebar, /AccountLink/);

  const utilitySidebar = readProjectFile("components/sidebar/UtilitySidebar.tsx");
  assert.match(utilitySidebar, /AccountLink/);
});

test("account page shows current user access from upstream multi-user API", () => {
  const page = readProjectFile("app/(utility)/account/page.tsx");
  assert.match(page, /fetchMyAccess/);

  const api = readProjectFile("features/multi-user/api.ts");
  assert.match(api, /\/api\/v1\/multi-user\/me\/access/);
});

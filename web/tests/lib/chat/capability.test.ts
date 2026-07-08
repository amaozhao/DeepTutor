import test from "node:test";
import assert from "node:assert/strict";

import {
  chatCapabilityMode,
  chatCapabilitySelectionPlan,
  chatCapabilityConfigStorageKey,
  chatDefaultLLMSelectionPlan,
  chatEnabledToolsSyncPlan,
  chatQueryCapabilityPlan,
  parsePersistedChatCapabilityConfig,
  shouldAutoOpenCapabilityConfig,
} from "../../../lib/chat/capability";
import type { CapabilityDef } from "../../../lib/capabilities";

const icon = (() => null) as never;
const capabilities: CapabilityDef[] = [
  {
    value: "",
    label: "Chat",
    description: "",
    icon,
    allowedTools: ["web_search", "reason"],
    defaultTools: [],
  },
  {
    value: "deep_solve",
    label: "Solve",
    description: "",
    icon,
    allowedTools: ["web_search"],
    defaultTools: [],
  },
];

test("chatCapabilityMode identifies config-backed capabilities", () => {
  assert.deepEqual(chatCapabilityMode(null), {
    isQuizMode: false,
    isVisualizeMode: false,
    isResearchMode: false,
    capabilityNeedsConfig: false,
  });
  assert.deepEqual(chatCapabilityMode("deep_question"), {
    isQuizMode: true,
    isVisualizeMode: false,
    isResearchMode: false,
    capabilityNeedsConfig: true,
  });
  assert.deepEqual(chatCapabilityMode("visualize"), {
    isQuizMode: false,
    isVisualizeMode: true,
    isResearchMode: false,
    capabilityNeedsConfig: true,
  });
  assert.deepEqual(chatCapabilityMode("deep_research"), {
    isQuizMode: false,
    isVisualizeMode: false,
    isResearchMode: true,
    capabilityNeedsConfig: true,
  });
});

test("shouldAutoOpenCapabilityConfig only opens on false-to-true transition", () => {
  assert.equal(shouldAutoOpenCapabilityConfig(false, true), true);
  assert.equal(shouldAutoOpenCapabilityConfig(false, false), false);
  assert.equal(shouldAutoOpenCapabilityConfig(true, true), false);
  assert.equal(shouldAutoOpenCapabilityConfig(true, false), false);
});

test("chatDefaultLLMSelectionPlan only fills missing selection", () => {
  const current = { profile_id: "custom", model_id: "m1" };
  const defaultSelection = { profile_id: "default", model_id: "m2" };

  assert.deepEqual(
    chatDefaultLLMSelectionPlan({ current: null, defaultSelection }),
    defaultSelection,
  );
  assert.equal(
    chatDefaultLLMSelectionPlan({ current, defaultSelection }),
    null,
  );
  assert.equal(
    chatDefaultLLMSelectionPlan({ current: null, defaultSelection: null }),
    null,
  );
});

test("chatCapabilityConfigStorageKey prefers loaded session id", () => {
  assert.equal(
    chatCapabilityConfigStorageKey("server-session", "url-session"),
    "dt:chat:capability-config:server-session",
  );
});

test("chatCapabilityConfigStorageKey falls back to URL session id", () => {
  assert.equal(
    chatCapabilityConfigStorageKey(null, "url-session"),
    "dt:chat:capability-config:url-session",
  );
});

test("chatCapabilityConfigStorageKey returns null without a session", () => {
  assert.equal(chatCapabilityConfigStorageKey("", null), null);
});

test("parsePersistedChatCapabilityConfig reads valid JSON", () => {
  const parsed = parsePersistedChatCapabilityConfig(
    JSON.stringify({
      capabilityConfigConfirmed: true,
      visualizeConfig: { render_mode: "svg", quality: "high", style_hint: "" },
    }),
  );

  assert.equal(parsed?.capabilityConfigConfirmed, true);
  assert.deepEqual(parsed?.visualizeConfig, {
    render_mode: "svg",
    quality: "high",
    style_hint: "",
  });
});

test("parsePersistedChatCapabilityConfig ignores empty or invalid entries", () => {
  assert.equal(parsePersistedChatCapabilityConfig(null), null);
  assert.equal(parsePersistedChatCapabilityConfig("{"), null);
});

test("chatCapabilitySelectionPlan uses saved playground tools and KB", () => {
  assert.deepEqual(
    chatCapabilitySelectionPlan({
      value: "deep_solve",
      capabilities,
      capabilityConfigs: {
        deep_solve: { enabledTools: ["reason"], knowledgeBase: "kb1" },
      },
      userEnabledTools: ["web_search"],
    }),
    {
      capability: capabilities[1],
      capabilityValue: "deep_solve",
      enabledTools: ["reason"],
      knowledgeBases: ["kb1"],
    },
  );
});

test("chatCapabilitySelectionPlan intersects user tools with capability tools", () => {
  assert.deepEqual(
    chatCapabilitySelectionPlan({
      value: "deep_solve",
      capabilities,
      capabilityConfigs: {},
      userEnabledTools: ["web_search", "reason"],
    }),
    {
      capability: capabilities[1],
      capabilityValue: "deep_solve",
      enabledTools: ["web_search"],
      knowledgeBases: [],
    },
  );
});

test("chatCapabilitySelectionPlan falls back to chat capability", () => {
  assert.deepEqual(
    chatCapabilitySelectionPlan({
      value: "missing",
      capabilities,
      capabilityConfigs: {},
      userEnabledTools: null,
    }),
    {
      capability: capabilities[0],
      capabilityValue: null,
      enabledTools: ["web_search", "reason"],
      knowledgeBases: [],
    },
  );
});

test("chatEnabledToolsSyncPlan filters user tools by capability", () => {
  assert.deepEqual(
    chatEnabledToolsSyncPlan({
      userEnabledTools: ["web_search", "reason"],
      allowedTools: ["web_search"],
      currentTools: [],
    }),
    ["web_search"],
  );
});

test("chatEnabledToolsSyncPlan returns null without changes", () => {
  assert.equal(
    chatEnabledToolsSyncPlan({
      userEnabledTools: null,
      allowedTools: ["web_search"],
      currentTools: [],
    }),
    null,
  );
  assert.equal(
    chatEnabledToolsSyncPlan({
      userEnabledTools: ["web_search"],
      allowedTools: ["web_search"],
      currentTools: ["web_search"],
    }),
    null,
  );
});

test("chatQueryCapabilityPlan prioritizes capability query", () => {
  assert.deepEqual(
    chatQueryCapabilityPlan({
      query: "?capability=deep_solve&tool=web_search",
      validTools: ["web_search"],
    }),
    { type: "capability", value: "deep_solve" },
  );
});

test("chatQueryCapabilityPlan filters and deduplicates tools", () => {
  assert.deepEqual(
    chatQueryCapabilityPlan({
      query: "?tool=web_search&tool=bad&tool=web_search&tool=reason",
      validTools: ["web_search", "reason"],
    }),
    { type: "tools", tools: ["web_search", "reason"] },
  );
});

test("chatQueryCapabilityPlan ignores empty query plans", () => {
  assert.equal(chatQueryCapabilityPlan({ query: "", validTools: [] }), null);
  assert.equal(
    chatQueryCapabilityPlan({ query: "?tool=bad", validTools: ["reason"] }),
    null,
  );
});

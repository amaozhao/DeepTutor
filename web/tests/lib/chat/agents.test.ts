import test from "node:test";
import assert from "node:assert/strict";

import {
  agentKnowledgeBaseNames,
  chatKnowledgeBaseOptions,
  connectedAgentOptions,
  selectedConnectedAgent,
  toggleKnowledgeBaseSelection,
  withoutConnectedAgents,
} from "../../../lib/chat/agents";

const knowledgeBases = [
  { name: "math" },
  { name: "codex-agent", metadata: { type: "subagent", agent_kind: "codex" } },
  {
    name: "claude-agent",
    metadata: { type: "subagent", agent_kind: "claude_code" },
  },
  { name: "notes", metadata: { type: "obsidian" } },
];

test("chatKnowledgeBaseOptions excludes connected agents", () => {
  assert.deepEqual(
    chatKnowledgeBaseOptions(knowledgeBases).map((kb) => kb.name),
    ["math", "notes"],
  );
});

test("connectedAgentOptions returns subagent name and kind", () => {
  assert.deepEqual(connectedAgentOptions(knowledgeBases), [
    { name: "codex-agent", kind: "codex" },
    { name: "claude-agent", kind: "claude_code" },
  ]);
});

test("selectedConnectedAgent and withoutConnectedAgents split selection", () => {
  const agents = agentKnowledgeBaseNames(knowledgeBases);

  assert.equal(
    selectedConnectedAgent(["math", "codex-agent"], agents),
    "codex-agent",
  );
  assert.deepEqual(withoutConnectedAgents(["math", "codex-agent"], agents), [
    "math",
  ]);
});

test("toggleKnowledgeBaseSelection adds and removes names", () => {
  assert.deepEqual(toggleKnowledgeBaseSelection(["math"], "notes"), [
    "math",
    "notes",
  ]);
  assert.deepEqual(toggleKnowledgeBaseSelection(["math", "notes"], "math"), [
    "notes",
  ]);
});

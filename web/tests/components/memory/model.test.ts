import test from "node:test";
import assert from "node:assert/strict";

import {
  entityAnchorId,
  entityDeepLinkUrl,
  formatTimestamp,
  labelFor,
  linkifyEntityRefs,
  parseEntityAnchor,
  shorten,
  type Entity,
} from "../../../components/memory/model";

test("entity refs round-trip through generated anchors", () => {
  const ref = "quiz:session:question";
  const anchor = entityAnchorId(ref);
  assert.equal(anchor, "entity-quiz__session__question");
  assert.deepEqual(parseEntityAnchor(anchor), {
    surface: "quiz",
    ref,
  });
  assert.equal(parseEntityAnchor("entity-unknown__1"), null);
});

test("linkifyEntityRefs converts supported memory refs", () => {
  assert.equal(
    linkifyEntityRefs("See chat:abc and kb:doc-1"),
    "See [chat:abc](#entity-chat__abc) and [kb:doc-1](#entity-kb__doc-1)",
  );
});

test("labelFor maps L2 surfaces and L3 slots", () => {
  assert.equal(labelFor({ layer: "L2", key: "chat" }), "Chat");
  assert.equal(labelFor({ layer: "L3", key: "preferences" }), "\u504f\u597d");
  assert.equal(labelFor({ layer: "L3", key: "custom" }), "custom");
});

test("shorten compacts whitespace and preserves short text", () => {
  assert.equal(shorten(" a   b ", 10), "a b");
  assert.equal(shorten("abcdef", 4), "abc\u2026");
});

test("entityDeepLinkUrl builds surface-specific destinations", () => {
  const entity = (id: string, metadata: Record<string, unknown> = {}) =>
    ({
      id,
      label: id,
      ts: "",
      content: "",
      metadata,
      fingerprint: "",
    }) satisfies Entity;

  assert.equal(entityDeepLinkUrl("chat", entity("s1")), "/home/s1");
  assert.equal(
    entityDeepLinkUrl("notebook", entity("r1", { notebook_id: "nb 1" })),
    "/space/notebooks?notebook=nb%201",
  );
  assert.equal(
    entityDeepLinkUrl("partner", entity("p1:session")),
    "/partners/p1",
  );
  assert.equal(
    entityDeepLinkUrl("quiz", entity("session:question")),
    "/?session=session",
  );
});

test("formatTimestamp keeps fallback and invalid values stable", () => {
  assert.equal(formatTimestamp(null, "fallback"), "fallback");
  assert.equal(formatTimestamp("not-a-date", "fallback"), "not-a-date");
});

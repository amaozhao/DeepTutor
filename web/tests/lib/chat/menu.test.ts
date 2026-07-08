import test from "node:test";
import assert from "node:assert/strict";

import { shouldCloseAnchoredMenu } from "../../../lib/chat/menu";

function region(inside: unknown[]) {
  return {
    contains(target: Node) {
      return inside.includes(target);
    },
  };
}

test("shouldCloseAnchoredMenu keeps menu open for menu or trigger clicks", () => {
  const menuTarget = {} as Node;
  const triggerTarget = {} as Node;

  assert.equal(
    shouldCloseAnchoredMenu({
      target: menuTarget,
      menu: region([menuTarget]),
      trigger: region([]),
    }),
    false,
  );
  assert.equal(
    shouldCloseAnchoredMenu({
      target: triggerTarget,
      menu: region([]),
      trigger: region([triggerTarget]),
    }),
    false,
  );
});

test("shouldCloseAnchoredMenu closes only when target is outside both anchors", () => {
  const target = {} as Node;

  assert.equal(
    shouldCloseAnchoredMenu({
      target,
      menu: region([]),
      trigger: region([]),
    }),
    true,
  );
});

test("shouldCloseAnchoredMenu ignores missing targets or anchors", () => {
  const target = {} as Node;

  assert.equal(
    shouldCloseAnchoredMenu({ target: null, menu: region([]), trigger: region([]) }),
    false,
  );
  assert.equal(
    shouldCloseAnchoredMenu({ target, menu: null, trigger: region([]) }),
    false,
  );
  assert.equal(
    shouldCloseAnchoredMenu({ target, menu: region([]), trigger: null }),
    false,
  );
});

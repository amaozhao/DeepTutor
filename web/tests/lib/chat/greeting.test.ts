import test from "node:test";
import assert from "node:assert/strict";

import { chatGreetingForHour } from "../../../lib/chat/greeting";

test("chatGreetingForHour selects the expected time bucket", () => {
  assert.equal(chatGreetingForHour(5, () => 0), "Good morning.");
  assert.equal(chatGreetingForHour(12, () => 0), "Good afternoon.");
  assert.equal(chatGreetingForHour(17, () => 0), "Good evening.");
  assert.equal(chatGreetingForHour(22, () => 0), "It's late today.");
  assert.equal(chatGreetingForHour(4, () => 0), "It's late today.");
});

test("chatGreetingForHour uses the injected random source", () => {
  assert.equal(
    chatGreetingForHour(9, () => 0.99),
    "What would you like to learn?",
  );
});

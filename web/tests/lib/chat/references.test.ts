import test from "node:test";
import assert from "node:assert/strict";

import {
  buildNotebookReferenceGroups,
  buildNotebookReferencesPayload,
  historyReferenceIds,
  uniqueHistoryReferenceIds,
} from "../../../lib/chat/references";

test("buildNotebookReferencesPayload groups record ids by notebook", () => {
  assert.deepEqual(
    buildNotebookReferencesPayload([
      { id: "r1", notebookId: "n1", notebookName: "Notebook 1" },
      { id: "r2", notebookId: "n2", notebookName: "Notebook 2" },
      { id: "r3", notebookId: "n1", notebookName: "Notebook 1" },
    ]),
    [
      { notebook_id: "n1", record_ids: ["r1", "r3"] },
      { notebook_id: "n2", record_ids: ["r2"] },
    ],
  );
});

test("buildNotebookReferenceGroups counts records per notebook", () => {
  assert.deepEqual(
    buildNotebookReferenceGroups([
      { id: "r1", notebookId: "n1", notebookName: "Notebook 1" },
      { id: "r2", notebookId: "n1", notebookName: "Notebook 1" },
      { id: "r3", notebookId: "n2", notebookName: "Notebook 2" },
    ]),
    [
      { notebookId: "n1", notebookName: "Notebook 1", count: 2 },
      { notebookId: "n2", notebookName: "Notebook 2", count: 1 },
    ],
  );
});

test("historyReferenceIds preserves the selected session order", () => {
  assert.deepEqual(
    historyReferenceIds([{ sessionId: "s1" }, { sessionId: "s2" }]),
    ["s1", "s2"],
  );
});

test("uniqueHistoryReferenceIds merges groups and drops duplicate sessions", () => {
  assert.deepEqual(
    uniqueHistoryReferenceIds(
      [{ sessionId: "s1" }, { sessionId: "s2" }],
      [{ sessionId: "s2" }, { sessionId: "s3" }],
    ),
    ["s1", "s2", "s3"],
  );
});

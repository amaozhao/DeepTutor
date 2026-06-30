import test from "node:test";
import assert from "node:assert/strict";

import { filenameFromContentDisposition } from "../features/multi-user/download";

test("filenameFromContentDisposition extracts quoted filenames", () => {
  assert.equal(
    filenameFromContentDisposition(
      'attachment; filename="deeptutor-user-alice-u1.zip"',
      "fallback.zip",
    ),
    "deeptutor-user-alice-u1.zip",
  );
});

test("filenameFromContentDisposition falls back when header is missing", () => {
  assert.equal(filenameFromContentDisposition(null, "fallback.zip"), "fallback.zip");
});

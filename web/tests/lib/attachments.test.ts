import test from "node:test";
import assert from "node:assert/strict";

import { filterAttachments } from "../../lib/attachments";

function file(name: string, size: number, type = "text/plain"): File {
  return new File(["x".repeat(size)], name, { type });
}

test("filterAttachments accepts supported files within the quota", () => {
  const accepted = filterAttachments(
    [file("notes.md", 10), file("image.png", 10, "image/png")],
    [],
  );

  assert.deepEqual(
    accepted.accepted.map((item) => item.name),
    ["notes.md", "image.png"],
  );
  assert.deepEqual(accepted.rejected, []);
});

test("filterAttachments honors runtime attachment limits", () => {
  const result = filterAttachments([file("notes.md", 6)], [], {
    maxFileBytes: 5,
    maxTotalBytes: 10,
  });

  assert.deepEqual(result.accepted, []);
  assert.deepEqual(result.rejected, [
    { name: "notes.md", reason: "too_large" },
  ]);
});

test("filterAttachments rejects unsupported, oversized, and quota overflow files", () => {
  const result = filterAttachments(
    [
      file("bad.exe", 10, "application/x-msdownload"),
      file("huge.md", 11 * 1024 * 1024),
      file("overflow.md", 2),
    ],
    [{ size: 25 * 1024 * 1024 - 1 }],
    {
      maxFileBytes: 10 * 1024 * 1024,
      maxTotalBytes: 25 * 1024 * 1024,
    },
  );

  assert.deepEqual(result.accepted, []);
  assert.deepEqual(result.rejected, [
    { name: "bad.exe", reason: "unsupported" },
    { name: "huge.md", reason: "too_large" },
    { name: "overflow.md", reason: "quota" },
  ]);
});

const Module = require("node:module");
const path = require("node:path");

const compiledRoot = path.resolve(__dirname, "..", "dist", "node-tests");
const originalResolveFilename = Module._resolveFilename;

Module._resolveFilename = function resolveNodeTestAlias(request, parent, isMain, options) {
  const resolvedRequest = request.startsWith("@/")
    ? path.join(compiledRoot, request.slice(2))
    : request;
  return originalResolveFilename.call(this, resolvedRequest, parent, isMain, options);
};

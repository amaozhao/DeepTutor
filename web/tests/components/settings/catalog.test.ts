import test from "node:test";
import assert from "node:assert/strict";

import {
  defaultCatalog,
  getActiveModel,
  getActiveProfile,
  nextModelName,
  serviceReadiness,
  type Catalog,
} from "../../../components/settings/catalog";

test("default catalog has every service bucket", () => {
  const catalog = defaultCatalog();
  assert.deepEqual(Object.keys(catalog.services).sort(), [
    "embedding",
    "imagegen",
    "llm",
    "search",
    "stt",
    "tts",
    "videogen",
  ]);
});

test("active profile and model fall back to first available item", () => {
  const catalog: Catalog = defaultCatalog();
  catalog.services.llm.profiles.push({
    id: "p1",
    name: "OpenAI",
    binding: "openai",
    base_url: "",
    api_key: "",
    api_version: "",
    models: [
      { id: "m1", name: "Model 1", model: "gpt-4o" },
      { id: "m2", name: "Model 2", model: "gpt-4.1" },
    ],
  });

  assert.equal(getActiveProfile(catalog, "llm")?.id, "p1");
  assert.equal(getActiveModel(catalog, "llm")?.id, "m1");
});

test("service readiness separates missing config from stale diagnostics", () => {
  const catalog: Catalog = defaultCatalog();
  assert.equal(serviceReadiness(catalog, "llm", {}), "not_configured");

  catalog.services.llm.active_profile_id = "p1";
  catalog.services.llm.active_model_id = "m1";
  catalog.services.llm.profiles.push({
    id: "p1",
    name: "OpenAI",
    binding: "openai",
    base_url: "",
    api_key: "",
    api_version: "",
    models: [{ id: "m1", name: "Model 1", model: "gpt-4o" }],
  });

  assert.equal(serviceReadiness(catalog, "llm", {}), "untested");
  assert.equal(
    serviceReadiness(catalog, "llm", {
      llm: {
        state: "success",
        message: "ok",
        profileId: "other",
        modelId: "m1",
      },
    }),
    "untested",
  );
  assert.equal(
    serviceReadiness(catalog, "llm", {
      llm: {
        state: "success",
        message: "ok",
        profileId: "p1",
        modelId: "m1",
      },
    }),
    "passed",
  );
});

test("next model name skips names already used", () => {
  assert.equal(
    nextModelName(
      [
        { id: "m1", name: "Model 2", model: "a" },
        { id: "m2", name: "Model 3", model: "b" },
      ],
      "en",
    ),
    "Model 4",
  );
});

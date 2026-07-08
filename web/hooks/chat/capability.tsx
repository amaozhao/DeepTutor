"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  DEFAULT_QUIZ_CONFIG,
  type DeepQuestionFormConfig,
} from "@/lib/quiz-types";
import {
  DEFAULT_VISUALIZE_CONFIG,
  type VisualizeFormConfig,
} from "@/lib/visualize-types";
import {
  createEmptyResearchConfig,
  validateResearchConfig,
  type DeepResearchFormConfig,
} from "@/lib/research-types";
import {
  chatEnabledToolsSyncPlan,
  chatCapabilityConfigStorageKey,
  chatQueryCapabilityPlan,
  parsePersistedChatCapabilityConfig,
  shouldAutoOpenCapabilityConfig,
} from "@/lib/chat/capability";

const CapabilityConfigCard = dynamic(
  () => import("@/components/chat/home/CapabilityConfigCard"),
  { ssr: false },
);
const QuizConfigPanel = dynamic(
  () => import("@/components/quiz/QuizConfigPanel"),
  { ssr: false },
);
const VisualizeConfigPanel = dynamic(
  () => import("@/components/visualize/VisualizeConfigPanel"),
  { ssr: false },
);
const ResearchConfigPanel = dynamic(
  () => import("@/components/research/ResearchConfigPanel"),
  { ssr: false },
);

type ChatCapabilityConfigInput = {
  sessionId: string | null;
  sessionIdParam: string | null;
  isQuizMode: boolean;
  isVisualizeMode: boolean;
  capabilityNeedsConfig: boolean;
};

export function useChatCapabilityConfigAutoOpen(
  capabilityNeedsConfig: boolean,
  ensureActivityPanelOpen: () => void,
) {
  const lastCapabilityNeedsConfigRef = useRef(capabilityNeedsConfig);
  useEffect(() => {
    const prev = lastCapabilityNeedsConfigRef.current;
    lastCapabilityNeedsConfigRef.current = capabilityNeedsConfig;
    if (shouldAutoOpenCapabilityConfig(prev, capabilityNeedsConfig)) {
      ensureActivityPanelOpen();
    }
  }, [capabilityNeedsConfig, ensureActivityPanelOpen]);
}

export function useChatEnabledToolsSync({
  userEnabledTools,
  allowedTools,
  currentTools,
  setTools,
}: {
  userEnabledTools: string[] | null;
  allowedTools: string[];
  currentTools: string[];
  setTools: (tools: string[]) => void;
}) {
  useEffect(() => {
    const next = chatEnabledToolsSyncPlan({
      userEnabledTools,
      allowedTools,
      currentTools,
    });
    if (next) setTools(next);
  }, [allowedTools, currentTools, setTools, userEnabledTools]);
}

export function useChatQueryCapabilityInitializer({
  allowedTools,
  onSelectCapability,
  setTools,
}: {
  allowedTools: string[];
  onSelectCapability: (value: string) => void;
  setTools: (tools: string[]) => void;
}) {
  const initializedRef = useRef(false);
  useEffect(() => {
    if (initializedRef.current) return;
    initializedRef.current = true;
    if (typeof window === "undefined") return;
    const plan = chatQueryCapabilityPlan({
      query: window.location.search,
      validTools: allowedTools,
    });
    if (plan?.type === "capability") onSelectCapability(plan.value);
    if (plan?.type === "tools") setTools(plan.tools);
  }, [allowedTools, onSelectCapability, setTools]);
}

export function useChatCapabilityConfig({
  sessionId,
  sessionIdParam,
  isQuizMode,
  isVisualizeMode,
  capabilityNeedsConfig,
}: ChatCapabilityConfigInput) {
  const [quizConfig, setQuizConfig] = useState<DeepQuestionFormConfig>({
    ...DEFAULT_QUIZ_CONFIG,
  });
  const [quizPdf, setQuizPdf] = useState<File | null>(null);
  const [visualizeConfig, setVisualizeConfig] = useState<VisualizeFormConfig>({
    ...DEFAULT_VISUALIZE_CONFIG,
  });
  const [researchConfig, setResearchConfig] = useState<DeepResearchFormConfig>(
    createEmptyResearchConfig(),
  );
  const [confirmed, setConfirmed] = useState(false);

  const storageKey = useMemo(() => {
    return chatCapabilityConfigStorageKey(sessionId, sessionIdParam);
  }, [sessionId, sessionIdParam]);
  const lastHydratedKeyRef = useRef<string | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!storageKey) return;
    if (lastHydratedKeyRef.current === storageKey) return;
    lastHydratedKeyRef.current = storageKey;
    const raw = window.localStorage.getItem(storageKey);
    if (!raw) return;
    const parsed = parsePersistedChatCapabilityConfig(raw);
    if (!parsed) return;
    if (parsed.quizConfig) {
      setQuizConfig(parsed.quizConfig as DeepQuestionFormConfig);
    }
    if (parsed.visualizeConfig) {
      setVisualizeConfig(parsed.visualizeConfig as VisualizeFormConfig);
    }
    if (parsed.researchConfig) {
      setResearchConfig(parsed.researchConfig as DeepResearchFormConfig);
    }
    if (typeof parsed.capabilityConfigConfirmed === "boolean") {
      setConfirmed(parsed.capabilityConfigConfirmed);
    }
  }, [storageKey]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!storageKey) return;
    window.localStorage.setItem(
      storageKey,
      JSON.stringify({
        quizConfig,
        visualizeConfig,
        researchConfig,
        capabilityConfigConfirmed: confirmed,
      }),
    );
  }, [storageKey, quizConfig, visualizeConfig, researchConfig, confirmed]);

  const changeQuizConfig = useCallback((next: DeepQuestionFormConfig) => {
    setQuizConfig(next);
    setConfirmed(false);
  }, []);

  const uploadQuizPdf = useCallback((file: File | null) => {
    setQuizPdf(file);
    setConfirmed(false);
  }, []);

  const changeVisualizeConfig = useCallback((next: VisualizeFormConfig) => {
    setVisualizeConfig(next);
    setConfirmed(false);
  }, []);

  const changeResearchConfig = useCallback((next: DeepResearchFormConfig) => {
    setResearchConfig(next);
    setConfirmed(false);
  }, []);

  const confirm = useCallback(() => {
    setConfirmed(true);
  }, []);

  const researchValidation = useMemo(
    () => validateResearchConfig(researchConfig),
    [researchConfig],
  );

  const configSection = useMemo(() => {
    if (!capabilityNeedsConfig) return null;
    if (isQuizMode) {
      return (
        <CapabilityConfigCard
          capability="deep_question"
          confirmed={confirmed}
          canConfirm
          onConfirm={confirm}
        >
          <QuizConfigPanel
            value={quizConfig}
            onChange={changeQuizConfig}
            uploadedPdf={quizPdf}
            onUploadPdf={uploadQuizPdf}
          />
        </CapabilityConfigCard>
      );
    }
    if (isVisualizeMode) {
      return (
        <CapabilityConfigCard
          capability="visualize"
          confirmed={confirmed}
          canConfirm
          onConfirm={confirm}
        >
          <VisualizeConfigPanel
            value={visualizeConfig}
            onChange={changeVisualizeConfig}
          />
        </CapabilityConfigCard>
      );
    }
    const researchErrorMessages = Object.values(researchValidation.errors);
    return (
      <CapabilityConfigCard
        capability="deep_research"
        confirmed={confirmed}
        canConfirm={researchErrorMessages.length === 0}
        validationErrors={researchErrorMessages}
        onConfirm={confirm}
      >
        <ResearchConfigPanel
          value={researchConfig}
          errors={researchValidation.errors}
          onChange={changeResearchConfig}
        />
      </CapabilityConfigCard>
    );
  }, [
    capabilityNeedsConfig,
    isQuizMode,
    isVisualizeMode,
    confirmed,
    confirm,
    quizConfig,
    quizPdf,
    changeQuizConfig,
    uploadQuizPdf,
    visualizeConfig,
    changeVisualizeConfig,
    researchConfig,
    researchValidation.errors,
    changeResearchConfig,
  ]);

  return {
    quizConfig,
    quizPdf,
    visualizeConfig,
    researchConfig,
    researchValidation,
    confirmed,
    setConfirmed,
    configSection,
  };
}

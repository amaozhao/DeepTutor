"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type RouterLike = {
  replace: (href: string, options?: { scroll?: boolean }) => void;
};

type ChatSessionRouteInput = {
  sessionId: string | null;
  sessionIdParam: string | null;
  router: RouterLike;
  newSession: () => void;
  loadSession: (sessionId: string, signal?: AbortSignal) => Promise<void>;
  setActiveSessionId: (sessionId: string | null) => void;
};

export function useChatSessionRoute({
  sessionId,
  sessionIdParam,
  router,
  newSession,
  loadSession,
  setActiveSessionId,
}: ChatSessionRouteInput) {
  const initialLoadRef = useRef(false);
  const prevSessionIdParam = useRef(sessionIdParam);
  const loadAbortRef = useRef<AbortController | null>(null);
  const [sessionLoading, setSessionLoading] = useState(false);

  const navigateToHome = useCallback(() => {
    router.replace("/home", { scroll: false });
  }, [router]);

  const cancelSessionLoad = useCallback(() => {
    loadAbortRef.current?.abort();
    loadAbortRef.current = null;
    setSessionLoading(false);
    navigateToHome();
  }, [navigateToHome]);

  const startSessionLoad = useCallback(
    (sid: string) => {
      loadAbortRef.current?.abort();
      const ctrl = new AbortController();
      loadAbortRef.current = ctrl;
      setSessionLoading(true);

      void loadSession(sid, ctrl.signal)
        .then(() => {
          if (!ctrl.signal.aborted) {
            loadAbortRef.current = null;
            setSessionLoading(false);
          }
        })
        .catch(() => {
          if (!ctrl.signal.aborted) {
            loadAbortRef.current = null;
            setSessionLoading(false);
            navigateToHome();
          }
        });
    },
    [loadSession, navigateToHome],
  );

  useEffect(() => {
    if (initialLoadRef.current) return;
    initialLoadRef.current = true;
    if (sessionIdParam) {
      startSessionLoad(sessionIdParam);
    } else {
      newSession();
    }
    return () => {
      initialLoadRef.current = false;
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (sessionIdParam === prevSessionIdParam.current) return;
    prevSessionIdParam.current = sessionIdParam;
    loadAbortRef.current?.abort();
    loadAbortRef.current = null;
    if (sessionIdParam) {
      if (sessionIdParam === sessionId) {
        setSessionLoading(false);
        return;
      }
      startSessionLoad(sessionIdParam);
    } else {
      newSession();
      setSessionLoading(false);
    }
  }, [sessionIdParam, startSessionLoad, newSession, sessionId]);

  useEffect(() => {
    if (sessionId && !sessionIdParam) {
      router.replace(`/home/${sessionId}`, { scroll: false });
    }
  }, [sessionId, sessionIdParam, router]);

  useEffect(() => {
    setActiveSessionId(sessionId || sessionIdParam || null);
  }, [sessionId, sessionIdParam, setActiveSessionId]);

  return {
    sessionLoading,
    cancelSessionLoad,
  };
}

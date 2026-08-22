"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  SESSION_LOAD_TIMEOUT_MS,
  shouldSurfaceLoadFailure,
} from "@/lib/session-load";

type RouterLike = {
  replace: (href: string, options?: { scroll?: boolean }) => void;
};

type ChatSessionRouteInput = {
  sessionId: string | null;
  sessionIdParam: string | null;
  router: RouterLike;
  newSession: () => void;
  loadSession: (
    sessionId: string,
    options?: { signal?: AbortSignal; revalidate?: boolean },
  ) => Promise<void>;
  showCachedSession: (sessionId: string) => boolean;
  setActiveSessionId: (sessionId: string | null) => void;
};

export function useChatSessionRoute({
  sessionId,
  sessionIdParam,
  router,
  newSession,
  loadSession,
  showCachedSession,
  setActiveSessionId,
}: ChatSessionRouteInput) {
  const initialLoadRef = useRef(false);
  const prevSessionIdParam = useRef(sessionIdParam);
  const loadAbortRef = useRef<AbortController | null>(null);
  const [sessionLoading, setSessionLoading] = useState(false);
  const [sessionLoadFailed, setSessionLoadFailed] = useState(false);

  const navigateToHome = useCallback(() => {
    router.replace("/home", { scroll: false });
  }, [router]);

  const cancelSessionLoad = useCallback(() => {
    loadAbortRef.current?.abort();
    loadAbortRef.current = null;
    setSessionLoading(false);
    setSessionLoadFailed(false);
    navigateToHome();
  }, [navigateToHome]);

  const startSessionLoad = useCallback(
    (sid: string) => {
      loadAbortRef.current?.abort();
      const ctrl = new AbortController();
      loadAbortRef.current = ctrl;
      const cached = showCachedSession(sid);
      setSessionLoading(!cached);
      setSessionLoadFailed(false);
      let timedOut = false;
      const timeout = setTimeout(() => {
        timedOut = true;
        ctrl.abort();
      }, SESSION_LOAD_TIMEOUT_MS);

      void loadSession(sid, { signal: ctrl.signal, revalidate: cached })
        .then(() => {
          clearTimeout(timeout);
          if (!ctrl.signal.aborted) {
            loadAbortRef.current = null;
            setSessionLoading(false);
          }
        })
        .catch(() => {
          clearTimeout(timeout);
          if (
            !shouldSurfaceLoadFailure({
              aborted: ctrl.signal.aborted,
              timedOut,
              cached,
            })
          )
            return;
          loadAbortRef.current = null;
          setSessionLoading(false);
          setSessionLoadFailed(true);
        });
    },
    [loadSession, showCachedSession],
  );

  const retrySessionLoad = useCallback(() => {
    if (sessionIdParam) startSessionLoad(sessionIdParam);
  }, [sessionIdParam, startSessionLoad]);

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
        setSessionLoadFailed(false);
        return;
      }
      startSessionLoad(sessionIdParam);
    } else {
      newSession();
      setSessionLoading(false);
      setSessionLoadFailed(false);
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
    sessionLoadFailed,
    cancelSessionLoad,
    retrySessionLoad,
  };
}

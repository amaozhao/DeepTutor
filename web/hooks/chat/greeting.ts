"use client";

import { useEffect, useState } from "react";

import { currentChatGreeting } from "@/lib/chat/greeting";

const FALLBACK_GREETING = "What would you like to learn?";

export function useChatWelcomeGreeting() {
  const [greeting, setGreeting] = useState(FALLBACK_GREETING);

  useEffect(() => {
    setGreeting(currentChatGreeting());
  }, []);

  return greeting;
}

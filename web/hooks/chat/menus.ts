"use client";

import { useEffect, useRef, useState } from "react";

import { shouldCloseAnchoredMenu } from "@/lib/chat/menu";

export function useChatComposerMenus() {
  const [capMenuOpen, setCapMenuOpen] = useState(false);
  const [spaceMenuOpen, setSpaceMenuOpen] = useState(false);
  const capMenuRef = useRef<HTMLDivElement>(null);
  const capBtnRef = useRef<HTMLButtonElement>(null);
  const spaceMenuRef = useRef<HTMLDivElement>(null);
  const spaceBtnRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!capMenuOpen && !spaceMenuOpen) return;
    const handler = (event: MouseEvent) => {
      const target = event.target as Node | null;
      if (
        capMenuOpen &&
        shouldCloseAnchoredMenu({
          target,
          menu: capMenuRef.current,
          trigger: capBtnRef.current,
        })
      ) {
        setCapMenuOpen(false);
      }
      if (
        spaceMenuOpen &&
        shouldCloseAnchoredMenu({
          target,
          menu: spaceMenuRef.current,
          trigger: spaceBtnRef.current,
        })
      ) {
        setSpaceMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [capMenuOpen, spaceMenuOpen]);

  return {
    capMenuRef,
    capBtnRef,
    spaceMenuRef,
    spaceBtnRef,
    capMenuOpen,
    spaceMenuOpen,
    setCapMenuOpen,
    setSpaceMenuOpen,
  };
}

export function chatMessagesScrollStyle(hasMessages: boolean):
  | {
      paddingBottom: string;
      WebkitMaskImage: string;
      maskImage: string;
    }
  | undefined {
  if (!hasMessages) return undefined;
  const maskImage =
    "linear-gradient(to bottom, transparent 0px, #000 32px, #000 calc(100% - 40px), transparent 100%)";
  return {
    paddingBottom: "48px",
    WebkitMaskImage: maskImage,
    maskImage,
  };
}

export function chatVisualizePromptFromEvent(event: Event): string | null {
  const text = (event as CustomEvent<unknown>).detail;
  return typeof text === "string" && text ? text : null;
}

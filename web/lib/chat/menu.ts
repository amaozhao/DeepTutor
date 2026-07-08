export function shouldCloseAnchoredMenu({
  target,
  menu,
  trigger,
}: {
  target: Node | null;
  menu: { contains(target: Node): boolean } | null | undefined;
  trigger: { contains(target: Node): boolean } | null | undefined;
}): boolean {
  if (!target || !menu || !trigger) return false;
  return !menu.contains(target) && !trigger.contains(target);
}

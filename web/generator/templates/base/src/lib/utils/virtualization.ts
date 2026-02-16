export interface VirtualItemLike {
  start: number;
  end: number;
}

export function getVirtualPadding(
  items: VirtualItemLike[],
  totalSize: number,
): { paddingTop: number; paddingBottom: number } {
  if (items.length === 0) {
    return { paddingTop: 0, paddingBottom: Math.max(totalSize, 0) };
  }

  const paddingTop = Math.max(items[0].start, 0);
  const last = items[items.length - 1];
  const paddingBottom = Math.max(totalSize - last.end, 0);

  return { paddingTop, paddingBottom };
}

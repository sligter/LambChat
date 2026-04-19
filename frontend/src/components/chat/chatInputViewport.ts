const DEFAULT_TEXTAREA_MAX_HEIGHT_PX = 250;
const DEFAULT_VIEWPORT_MARGIN_PX = 16;
const DEFAULT_KEYBOARD_THRESHOLD_PX = 80;

interface TextareaLike {
  style: {
    height: string;
  };
  scrollHeight: number;
  scrollTop: number;
}

interface VisibleElementLike {
  getBoundingClientRect: () => {
    top: number;
    bottom: number;
  };
  scrollIntoView?: (options?: ScrollIntoViewOptions) => void;
}

interface VisualViewportLike {
  offsetTop: number;
  height: number;
}

export function resizeTextareaForContent(
  textarea: TextareaLike,
  maxHeightPx = DEFAULT_TEXTAREA_MAX_HEIGHT_PX,
): void {
  textarea.style.height = "auto";
  textarea.style.height = `${Math.min(textarea.scrollHeight, maxHeightPx)}px`;
  textarea.scrollTop = textarea.scrollHeight;
}

export function keepElementVisibleInViewport({
  element,
  viewport,
  marginPx = DEFAULT_VIEWPORT_MARGIN_PX,
}: {
  element: VisibleElementLike;
  viewport?: VisualViewportLike | null;
  marginPx?: number;
}): boolean {
  const rect = element.getBoundingClientRect();
  const viewportTop = viewport?.offsetTop ?? 0;
  const viewportBottom =
    viewportTop +
    (viewport?.height ??
      (typeof window !== "undefined" ? window.innerHeight : rect.bottom));

  if (
    rect.top >= viewportTop + marginPx &&
    rect.bottom <= viewportBottom - marginPx
  ) {
    return false;
  }

  element.scrollIntoView?.({
    block: "nearest",
    inline: "nearest",
    behavior: "auto",
  });
  return true;
}

export function getKeyboardInsetPx({
  windowHeight,
  viewport,
  thresholdPx = DEFAULT_KEYBOARD_THRESHOLD_PX,
}: {
  windowHeight: number;
  viewport?: VisualViewportLike | null;
  thresholdPx?: number;
}): number {
  if (!viewport) {
    return 0;
  }

  const inset = Math.max(
    0,
    windowHeight - viewport.height - viewport.offsetTop,
  );
  return inset >= thresholdPx ? Math.round(inset) : 0;
}

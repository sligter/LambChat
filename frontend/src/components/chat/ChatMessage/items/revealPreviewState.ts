import type { RevealPreviewRequest } from "./revealPreviewData";

export type RevealPreviewOpenSource = "auto" | "manual" | "external";

export interface ActiveRevealPreviewState {
  request: RevealPreviewRequest;
  source: RevealPreviewOpenSource;
  userInteracted: boolean;
}

export function createActiveRevealPreviewState(
  request: RevealPreviewRequest,
  source: RevealPreviewOpenSource,
): ActiveRevealPreviewState {
  return {
    request,
    source,
    userInteracted: source !== "auto",
  };
}

export function markRevealPreviewInteracted(
  preview: ActiveRevealPreviewState | null,
): ActiveRevealPreviewState | null {
  if (!preview || preview.userInteracted) {
    return preview;
  }

  return {
    ...preview,
    userInteracted: true,
  };
}

export function shouldAcceptRevealPreviewOpen(input: {
  activePreview: ActiveRevealPreviewState | null;
  nextPreview: RevealPreviewRequest;
  source: RevealPreviewOpenSource;
  dismissedPreviewKeys?: Set<string>;
}): boolean {
  const { activePreview, nextPreview, source, dismissedPreviewKeys } = input;

  if (source === "manual" || source === "external") {
    return true;
  }

  if (dismissedPreviewKeys?.has(nextPreview.previewKey)) {
    return false;
  }

  if (
    activePreview &&
    activePreview.request.kind === nextPreview.kind &&
    activePreview.request.previewKey === nextPreview.previewKey
  ) {
    return false;
  }

  if (!activePreview) {
    return true;
  }

  return activePreview.source === "auto" && !activePreview.userInteracted;
}

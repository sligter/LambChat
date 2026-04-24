export interface ExternalNavigationState {
  externalNavigate?: boolean;
  scrollToBottom?: boolean;
}

export function shouldResetExternalNavigateFlag(
  locationState: ExternalNavigationState | null | undefined,
): boolean {
  return locationState?.externalNavigate === true;
}

export function shouldScrollToBottomAfterExternalNavigation(
  locationState: ExternalNavigationState | null | undefined,
): boolean {
  return (
    locationState?.externalNavigate === true &&
    locationState?.scrollToBottom === true
  );
}

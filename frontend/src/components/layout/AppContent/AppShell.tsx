import { useEffect, type ReactNode } from "react";
import { ProfileModal } from "../../profile/ProfileModal";
import { Header } from "./Header";
import {
  getAppViewportHeightCssValue,
  shouldUpdateAppViewportHeight,
} from "./appViewport";
import type { Project, VersionInfo } from "../../../types";
import type { TabType } from "./types";

export interface AppShellProps {
  activeTab: TabType;
  showProfileModal: boolean;
  onCloseProfileModal: () => void;
  versionInfo: VersionInfo | null;
  setMobileSidebarOpen: (open: boolean) => void;
  currentProjectId: string | null;
  projectManager: { projects: Project[] };
  onNewSession: () => void;
  onShowProfile: () => void;
  sidebar?: ReactNode;
  children: ReactNode;
  // Model selection
  availableModels?:
    | {
        id: string;
        value: string;
        provider?: string;
        label: string;
        description?: string;
      }[]
    | null;
  currentModelId?: string;
  onSelectModel?: (modelId: string, modelValue: string) => void;
  // Share
  sessionId?: string | null;
  sessionName?: string | null;
  // Outline
  showOutlineButton?: boolean;
  onToggleOutline?: () => void;
}

export function AppShell({
  activeTab,
  showProfileModal,
  onCloseProfileModal,
  versionInfo,
  setMobileSidebarOpen,
  currentProjectId,
  projectManager,
  onNewSession,
  onShowProfile,
  sidebar,
  children,
  availableModels,
  currentModelId,
  onSelectModel,
  sessionId,
  sessionName,
  showOutlineButton,
  onToggleOutline,
}: AppShellProps) {
  useEffect(() => {
    if (typeof window === "undefined") return undefined;

    const rootStyle = document.documentElement.style;
    let raf = 0;
    let viewportHeightValue = "";

    const updateViewportHeight = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const nextViewportHeightValue = getAppViewportHeightCssValue({
          visualViewportHeight: window.visualViewport?.height ?? null,
          windowInnerHeight: window.innerHeight,
        });

        if (
          shouldUpdateAppViewportHeight(
            viewportHeightValue,
            nextViewportHeightValue,
          )
        ) {
          viewportHeightValue = nextViewportHeightValue;
          rootStyle.setProperty(
            "--app-viewport-height",
            nextViewportHeightValue,
          );
        }
      });
    };

    updateViewportHeight();
    window.visualViewport?.addEventListener("resize", updateViewportHeight);
    window.addEventListener("resize", updateViewportHeight);
    window.addEventListener("orientationchange", updateViewportHeight);

    return () => {
      cancelAnimationFrame(raf);
      window.visualViewport?.removeEventListener(
        "resize",
        updateViewportHeight,
      );
      window.removeEventListener("resize", updateViewportHeight);
      window.removeEventListener("orientationchange", updateViewportHeight);
      rootStyle.removeProperty("--app-viewport-height");
    };
  }, []);

  return (
    <>
      <ProfileModal
        showProfileModal={showProfileModal}
        onCloseProfileModal={onCloseProfileModal}
        versionInfo={versionInfo}
      />

      <div
        className="flex w-full overflow-hidden"
        style={{
          backgroundColor: "var(--theme-bg)",
          height: "var(--app-viewport-height, 100dvh)",
        }}
      >
        {sidebar}

        <div className="relative z-0 flex flex-1 min-w-0 flex-col overflow-hidden">
          <Header
            activeTab={activeTab}
            setMobileSidebarOpen={setMobileSidebarOpen}
            currentProjectId={currentProjectId}
            projectManager={projectManager}
            onNewSession={onNewSession}
            onShowProfile={onShowProfile}
            availableModels={availableModels}
            currentModelId={currentModelId}
            onSelectModel={onSelectModel}
            sessionId={sessionId}
            sessionName={sessionName}
            showOutlineButton={showOutlineButton}
            onToggleOutline={onToggleOutline}
          />

          {children}
        </div>
      </div>
    </>
  );
}

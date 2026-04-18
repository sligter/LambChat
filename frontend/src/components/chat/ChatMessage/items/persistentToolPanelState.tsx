/* eslint-disable react-refresh/only-export-components */
import { useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import type { CollapsibleStatus } from "../../../common/CollapsiblePill";
import { ToolResultPanel } from "./ToolResultPanel";
import { closeCurrentToolPanel } from "./toolPanelRegistry";

export interface PersistentToolPanelState {
  title: string;
  status: CollapsibleStatus;
  children: ReactNode;
  icon?: ReactNode;
  subtitle?: string;
  viewMode?: "sidebar" | "center";
  headerActions?: ReactNode;
  customHeader?: ReactNode;
  footer?: ReactNode;
  overlayClass?: string;
  panelClass?: string;
  onUserInteraction?: () => void;
}

const listeners = new Set<() => void>();
let currentPanel: PersistentToolPanelState | null = null;

function emit() {
  listeners.forEach((listener) => listener());
}

export function getPersistentToolPanelState(): PersistentToolPanelState | null {
  return currentPanel;
}

export function openPersistentToolPanel(panel: PersistentToolPanelState): void {
  closeCurrentToolPanel();
  currentPanel = panel;
  emit();
}

export function closePersistentToolPanel(): void {
  if (!currentPanel) return;
  currentPanel = null;
  emit();
}

function usePersistentToolPanel() {
  const [, forceRender] = useState(0);

  useEffect(() => {
    const listener = () => forceRender((count) => count + 1);
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  }, []);

  return {
    panel: currentPanel,
    close: closePersistentToolPanel,
  };
}

export function PersistentToolPanelHost() {
  const { panel, close } = usePersistentToolPanel();

  if (!panel) return null;

  return createPortal(
    <ToolResultPanel
      open={true}
      onClose={close}
      title={panel.title}
      icon={panel.icon}
      status={panel.status}
      subtitle={panel.subtitle}
      viewMode={panel.viewMode}
      headerActions={panel.headerActions}
      customHeader={panel.customHeader}
      footer={panel.footer}
      overlayClass={panel.overlayClass}
      panelClass={panel.panelClass}
      onUserInteraction={panel.onUserInteraction}
    >
      {panel.children}
    </ToolResultPanel>,
    document.body,
  );
}

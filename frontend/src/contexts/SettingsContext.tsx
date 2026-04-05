import { createContext, useContext, ReactNode, useMemo } from "react";
import { useSettings } from "../hooks/useSettings";
import type { SettingsResponse } from "../types";

export interface AvailableModel {
  value: string;
  label: string;
}

interface SettingsContextValue {
  settings: SettingsResponse | null;
  enableSkills: boolean;
  isLoading: boolean;
  error: string | null;
  savingKeys: Set<string>;
  availableModels: AvailableModel[] | null;
  defaultModel: string;
  updateSetting: (
    key: string,
    value: string | number | boolean | object,
  ) => Promise<boolean>;
  resetSetting: (key: string) => Promise<boolean>;
  resetAllSettings: () => Promise<boolean>;
  clearError: () => void;
  exportSettings: () => void;
  importSettings: (
    file: File,
  ) => Promise<{ success: boolean; updatedCount: number; errors: string[] }>;
}

const SettingsContext = createContext<SettingsContextValue | undefined>(
  undefined,
);

export function SettingsProvider({ children }: { children: ReactNode }) {
  const {
    settings,
    isLoading,
    error,
    savingKeys,
    getBooleanSetting,
    getSettingValue,
    updateSetting,
    resetSetting,
    resetAllSettings,
    clearError,
    exportSettings,
    importSettings,
  } = useSettings();

  const availableModels = useMemo(() => {
    const raw = getSettingValue("LLM_AVAILABLE_MODELS");
    if (Array.isArray(raw) && raw.length > 0) {
      return raw as AvailableModel[];
    }
    return null; // null = model selection disabled
  }, [getSettingValue]);

  const defaultModel = useMemo(() => {
    return (
      (getSettingValue("LLM_MODEL") as string) ||
      "anthropic/claude-3-5-sonnet-20241022"
    );
  }, [getSettingValue]);

  const value: SettingsContextValue = {
    settings,
    enableSkills: getBooleanSetting("ENABLE_SKILLS"),
    availableModels,
    defaultModel,
    isLoading,
    error,
    savingKeys,
    updateSetting,
    resetSetting,
    resetAllSettings,
    clearError,
    exportSettings,
    importSettings,
  };

  return (
    <SettingsContext.Provider value={value}>
      {children}
    </SettingsContext.Provider>
  );
}

// Fast refresh only works when a file only exports components.
// Use a new file to share constants or functions between components
// eslint-disable-next-line react-refresh/only-export-components
export function useSettingsContext() {
  const context = useContext(SettingsContext);
  if (context === undefined) {
    throw new Error(
      "useSettingsContext must be used within a SettingsProvider",
    );
  }
  return context;
}

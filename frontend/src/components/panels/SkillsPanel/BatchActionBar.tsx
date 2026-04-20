import { useTranslation } from "react-i18next";
import { Power, Zap, Trash2, X } from "lucide-react";
import { LoadingSpinner } from "../../common/LoadingSpinner";

interface BatchActionBarProps {
  selectedCount: number;
  batchLoading: boolean;
  onBatchToggle: (enabled: boolean) => void;
  onBatchDelete: () => void;
  onClearSelection: () => void;
}

export function BatchActionBar({
  selectedCount,
  batchLoading,
  onBatchToggle,
  onBatchDelete,
  onClearSelection,
}: BatchActionBarProps) {
  const { t } = useTranslation();

  return (
    <div className="fixed bottom-0 left-0 right-0 z-40 border-t border-[var(--theme-border)] bg-[var(--theme-bg-card)]/95 px-4 py-3 shadow-lg backdrop-blur-sm sm:left-auto sm:right-auto sm:mx-auto sm:max-w-3xl sm:rounded-t-2xl">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm text-[var(--theme-text)]">
          <span className="inline-flex h-6 min-w-6 items-center justify-center rounded-full bg-[var(--theme-primary)] px-1.5 text-[11px] font-bold text-white">
            {selectedCount}
          </span>
          <span className="text-[var(--theme-text-secondary)]">
            {t("skills.batchSelected")}
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => onBatchToggle(false)}
            disabled={batchLoading}
            className="btn-secondary"
          >
            <Power size={14} />
            <span className="hidden sm:inline">{t("skills.card.disable")}</span>
          </button>
          <button
            onClick={() => onBatchToggle(true)}
            disabled={batchLoading}
            className="btn-secondary"
          >
            <Zap size={14} />
            <span className="hidden sm:inline">{t("skills.card.enable")}</span>
          </button>
          <button
            onClick={onBatchDelete}
            disabled={batchLoading}
            className="btn-danger"
          >
            {batchLoading ? (
              <LoadingSpinner
                size="sm"
                color="text-red-600 dark:text-red-400"
              />
            ) : (
              <Trash2 size={14} />
            )}
            <span className="hidden sm:inline">{t("common.delete")}</span>
          </button>
          <button onClick={onClearSelection} className="btn-secondary">
            <X size={14} />
            <span className="hidden sm:inline">{t("common.cancel")}</span>
          </button>
        </div>
      </div>
    </div>
  );
}

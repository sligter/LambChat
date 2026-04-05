import { memo, useState, useCallback, useEffect, useRef } from "react";
import { ChevronDown, Check, Zap } from "lucide-react";

export interface ModelOption {
  value: string;
  label: string;
}

interface ModelItemProps {
  model: ModelOption;
  isSelected: boolean;
  onSelect: () => void;
}

const ModelItem = memo(function ModelItem({
  model,
  isSelected,
  onSelect,
}: ModelItemProps) {
  return (
    <button
      onClick={onSelect}
      className="w-full px-3 py-3 sm:py-4 text-left hover:bg-stone-100/80 dark:hover:bg-stone-700/50 transition-colors"
    >
      <div className="flex items-center gap-3">
        <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-stone-100 to-stone-200 dark:from-stone-700/60 dark:to-stone-600/40">
          <Zap size={18} className="text-stone-600 dark:text-amber-400" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium text-stone-700 dark:text-stone-200">
            {model.label}
          </div>
          <div className="text-xs text-stone-400 dark:text-stone-500 truncate">
            {model.value}
          </div>
        </div>
        {isSelected && (
          <Check
            size={18}
            className="flex-shrink-0 text-stone-600 dark:text-stone-400"
          />
        )}
      </div>
    </button>
  );
});

interface ModelSelectorProps {
  models: ModelOption[];
  currentModel: string;
  onSelectModel: (modelValue: string) => void;
}

const ModelSelector = memo(function ModelSelector({
  models,
  currentModel,
  onSelectModel,
}: ModelSelectorProps) {
  const [showSelector, setShowSelector] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const currentModelInfo = models.find((m) => m.value === currentModel);

  const handleSelectModel = useCallback(
    (modelValue: string) => {
      onSelectModel(modelValue);
      setShowSelector(false);
    },
    [onSelectModel],
  );

  const toggleSelector = useCallback(() => {
    setShowSelector((prev) => !prev);
  }, []);

  useEffect(() => {
    if (!showSelector) return;

    const handleClickOutside = (event: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setShowSelector(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [showSelector]);

  if (models.length === 0) return null;

  return (
    <div
      ref={containerRef}
      className="relative"
      onClick={(e) => e.stopPropagation()}
    >
      <button
        onClick={toggleSelector}
        className="flex items-center gap-1.5 hover:opacity-70 transition-opacity"
      >
        <span className="text-base font-semibold text-stone-600 dark:text-stone-300">
          {currentModelInfo?.label || currentModel}
        </span>
        <ChevronDown
          size={16}
          className={`text-stone-400 dark:text-stone-300 transition-transform duration-200 ${
            showSelector ? "rotate-180" : ""
          }`}
        />
      </button>

      {showSelector && (
        <div className="absolute left-0 top-full z-50 mt-2 w-72 rounded-xl bg-white dark:bg-stone-800 shadow-lg border border-stone-200 dark:border-stone-700 overflow-hidden animate-in fade-in-0 zoom-in-95 duration-150">
          {models.map((model) => (
            <ModelItem
              key={model.value}
              model={model}
              isSelected={model.value === currentModel}
              onSelect={() => handleSelectModel(model.value)}
            />
          ))}
        </div>
      )}
    </div>
  );
});

export { ModelSelector };

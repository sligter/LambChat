/**
 * Model selector for channel configuration.
 * Fetches user's available models and renders a select dropdown.
 * Uses model.id (DB ID) so the backend resolves provider/key/config.
 */
import { useState, useEffect } from "react";
import { Cpu, ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";
import { modelApi } from "../../../services/api/model";
import type { ModelConfig } from "../../../services/api/model";

interface ChannelModelSelectProps {
  value: string | null | undefined;
  onChange: (modelId: string | null) => void;
}

export function ChannelModelSelect({
  value,
  onChange,
}: ChannelModelSelectProps) {
  const { t } = useTranslation();
  const [models, setModels] = useState<ModelConfig[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    modelApi
      .listAvailable()
      .then((res) => {
        setModels(res.models || []);
      })
      .catch(() => {
        setModels([]);
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-1.5">
      <label className="block text-sm font-medium text-stone-700 dark:text-stone-300">
        <div className="flex items-center gap-1.5">
          <Cpu size={14} />
          {t("channel.model", "Model")}
        </div>
      </label>
      <div className="relative">
        <select
          value={value || ""}
          onChange={(e) => onChange(e.target.value || null)}
          disabled={loading}
          className="w-full appearance-none rounded-lg border border-stone-300 bg-white pl-3 pr-9 py-2 text-sm text-stone-900 focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500 dark:border-stone-600 dark:bg-stone-800 dark:text-stone-100"
        >
          <option value="">
            {loading
              ? t("common.loading", "Loading...")
              : t("channel.defaultModel", "Default Model")}
          </option>
          {models.map((model) => (
            <option key={model.id} value={model.id}>
              {model.label} ({model.value})
            </option>
          ))}
        </select>
        <ChevronDown
          size={16}
          className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-stone-400"
        />
      </div>
      <p className="text-xs text-stone-500 dark:text-stone-500">
        {t(
          "channel.modelHint",
          "Select which model this channel uses. Uses the model's configured provider and API key."
        )}
      </p>
    </div>
  );
}

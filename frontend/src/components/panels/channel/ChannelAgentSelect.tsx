/**
 * Agent selector for channel configuration.
 * Fetches user's available agents and renders a select dropdown.
 */
import { useState, useEffect } from "react";
import { Bot } from "lucide-react";
import { useTranslation } from "react-i18next";
import { agentApi } from "../../../services/api/agent";
import type { AgentInfo } from "../../../types";

interface ChannelAgentSelectProps {
  value: string | null | undefined;
  onChange: (agentId: string | null) => void;
}

export function ChannelAgentSelect({
  value,
  onChange,
}: ChannelAgentSelectProps) {
  const { t } = useTranslation();
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    agentApi
      .list()
      .then((res) => {
        setAgents(res.agents || []);
      })
      .catch(() => {
        setAgents([]);
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-1.5">
      <label className="block text-sm font-medium text-gray-700 dark:text-stone-300">
        <div className="flex items-center gap-1.5">
          <Bot size={14} />
          {t("channel.agent", "Agent")}
        </div>
      </label>
      <select
        value={value || ""}
        onChange={(e) => onChange(e.target.value || null)}
        disabled={loading}
        className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500 dark:border-stone-600 dark:bg-stone-800 dark:text-stone-100"
      >
        <option value="">
          {loading
            ? t("common.loading", "Loading...")
            : t("channel.defaultAgent", "Default Agent")}
        </option>
        {agents.map((agent) => (
          <option key={agent.id} value={agent.id}>
            {t(agent.name)} — {t(agent.description)}
          </option>
        ))}
      </select>
      <p className="text-xs text-gray-500 dark:text-stone-500">
        {t(
          "channel.agentHint",
          "Select which agent handles messages from this channel",
        )}
      </p>
    </div>
  );
}

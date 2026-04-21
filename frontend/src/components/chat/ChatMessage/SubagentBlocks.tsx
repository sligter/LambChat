import { useEffect, useState, useCallback } from "react";
import { clsx } from "clsx";
import {
  CheckCircle,
  XCircle,
  Ban,
  ChevronRight,
  Brain,
  Users,
  Box,
  Loader2,
  PanelRight,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { LoadingSpinner, CollapsiblePill } from "../../common";
import type { CollapsibleStatus } from "../../common";
import type { MessagePart } from "../../../types";
import { MarkdownContent } from "./MarkdownContent";
import { MessagePartRenderer } from "./MessagePartRenderer";
import {
  openPersistentToolPanel,
  updatePersistentToolPanel,
  isPersistentToolPanelOpen,
} from "./items/persistentToolPanelState";

// ==========================================
// Reactive subagent panel data store
// ==========================================

interface SubagentPanelData {
  agentId: string;
  agentName: string;
  input: string;
  result?: string;
  success?: boolean;
  error?: string;
  isPending?: boolean;
  parts?: MessagePart[];
  startedAt?: number;
  completedAt?: number;
  status?: "pending" | "running" | "complete" | "error" | "cancelled";
}

const subagentDataStore = new Map<string, SubagentPanelData>();
const subagentDataListeners = new Set<() => void>();

function emitSubagentDataChange() {
  subagentDataListeners.forEach((fn) => fn());
}

function setSubagentPanelData(data: SubagentPanelData) {
  subagentDataStore.set(data.agentId, data);
  emitSubagentDataChange();
}

function useSubagentPanelData(agentId: string): SubagentPanelData | undefined {
  const [, forceRender] = useState(0);

  useEffect(() => {
    const listener = () => forceRender((n) => n + 1);
    subagentDataListeners.add(listener);
    return () => {
      subagentDataListeners.delete(listener);
    };
  }, []);

  return subagentDataStore.get(agentId);
}

// ==========================================
// Subagent panel content (reactive)
// ==========================================

function SubagentPanelContent({ agentId }: { agentId: string }) {
  const { t } = useTranslation();
  const data = useSubagentPanelData(agentId);

  if (!data) return null;

  const effectiveStatus =
    data.status ||
    (data.isPending ? "running" : data.success ? "complete" : "error");

  return (
    <div className="space-y-3 max-h-[80vh] overflow-y-auto p-1">
      {data.input && (
        <div className="p-3 sm:p-4 rounded-lg bg-stone-50 dark:bg-stone-800/50">
          <div className="text-xs uppercase tracking-wider text-stone-400 dark:text-stone-500 mb-2 font-medium">
            {t("chat.message.args")}
          </div>
          <div className="text-sm text-stone-600 dark:text-stone-300 leading-relaxed">
            <MarkdownContent content={data.input} />
          </div>
        </div>
      )}
      {data.parts && data.parts.length > 0 && (
        <div className="space-y-2 pl-3 border-l-2 border-stone-200 dark:border-stone-700">
          {data.parts.map((part, index) => (
            <MessagePartRenderer
              key={index}
              part={part}
              isStreaming={data.isPending}
              isLast={index === data.parts!.length - 1}
            />
          ))}
        </div>
      )}
      {data.error && effectiveStatus === "error" && (
        <div className="p-3 sm:p-4 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-900/50">
          <div className="text-xs text-red-600 dark:text-red-400 font-medium mb-1">
            {t("chat.message.error")}
          </div>
          <div className="text-xs text-red-700 dark:text-red-300 leading-relaxed">
            {data.error}
          </div>
        </div>
      )}
      {data.result && effectiveStatus === "complete" && (
        <div className="p-3 sm:p-4 rounded-lg bg-stone-50 dark:bg-stone-800/50">
          <div className="text-xs uppercase tracking-wider text-stone-400 dark:text-stone-500 mb-2 font-medium">
            {t("chat.message.result")}
          </div>
          <div className="text-sm text-stone-700 dark:text-stone-300 leading-relaxed">
            <MarkdownContent content={data.result} />
          </div>
        </div>
      )}
      {data.isPending && !data.parts?.length && (
        <div className="flex items-center gap-2 text-stone-500 dark:text-stone-400">
          <LoadingSpinner size="sm" />
          <span className="text-sm">{t("chat.message.executing")}</span>
        </div>
      )}
    </div>
  );
}

// ==========================================
// Utility
// ==========================================

/**
 * Calculate elapsed time between start and end (precise to milliseconds)
 */
function getElapsedTime(
  startedAt: number | undefined,
  completedAt: number | undefined,
): string | null {
  if (!startedAt) return null;
  const end = completedAt ?? Date.now();
  const ms = end - startedAt;
  if (ms < 1000) return `${ms}ms`;
  const totalSeconds = Math.floor(ms / 1000);
  if (totalSeconds < 60) return `${totalSeconds}s`;
  const minutes = Math.floor(totalSeconds / 60);
  const remainingSeconds = totalSeconds % 60;
  return `${minutes}m ${remainingSeconds}s`;
}

// Thinking Block - thinking process display (ChatGPT style)
export function ThinkingBlock({
  content,
  isStreaming,
  isPending,
  success,
  hasResult,
}: {
  content: string;
  isStreaming?: boolean;
  isPending?: boolean;
  success?: boolean;
  hasResult?: boolean;
}) {
  const { t } = useTranslation();
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div className="my-1">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className={clsx(
          "inline-flex items-center gap-1 sm:gap-2 px-2.5 py-2 rounded-full text-xs font-medium",
          "transition-colors bg-stone-200 dark:bg-stone-700",
          "text-stone-600 dark:text-stone-300",
          "hover:bg-stone-300 dark:hover:bg-stone-600 cursor-pointer",
        )}
      >
        {/* Status indicator */}
        {isPending ? (
          <LoadingSpinner
            size="sm"
            className="shrink-0"
            color="text-[var(--theme-primary)]"
          />
        ) : success ? (
          <CheckCircle size={12} className="shrink-0" />
        ) : hasResult ? (
          <XCircle size={12} className="shrink-0" />
        ) : null}

        {/* Thinking icon */}
        <Brain
          size={12}
          className="shrink-0 text-stone-500 dark:text-stone-400"
        />

        <span className="font-mono">
          {isStreaming || isPending
            ? t("chat.message.thinking")
            : t("chat.message.thought")}
        </span>
        {isStreaming && (
          <span className="flex items-center gap-[2px] ml-1">
            <span className="w-0.5 h-1 bg-stone-500 dark:bg-stone-400 rounded-full animate-[wave_0.6s_ease-in-out_infinite]" />
            <span className="w-0.5 h-1.5 bg-stone-500 dark:bg-stone-400 rounded-full animate-[wave_0.6s_ease-in-out_infinite_0.1s]" />
            <span className="w-0.5 h-1 bg-stone-500 dark:bg-stone-400 rounded-full animate-[wave_0.6s_ease-in-out_infinite_0.2s]" />
          </span>
        )}
        <ChevronRight
          size={12}
          className={clsx(
            "shrink-0 transition-transform duration-200 text-stone-500 dark:text-stone-400",
            isExpanded && "rotate-90",
          )}
        />
      </button>

      {isExpanded && (
        <div className="mt-1 animate-[fade-in_150ms_ease-out]">
          <div className="ml-4 pl-3 border-l-2 border-stone-300 dark:border-stone-600">
            <div className="text-xs text-stone-600 dark:text-stone-300 leading-relaxed pl-1 pt-2">
              <MarkdownContent content={content} isStreaming={isStreaming} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Subagent Block - compact card, content always in sidebar panel
export function SubagentBlock({
  agent_id,
  agent_name,
  input,
  result,
  success,
  isPending,
  parts,
  startedAt,
  completedAt,
  status,
  error,
}: {
  agent_id: string;
  agent_name: string;
  input: string;
  result?: string;
  success?: boolean;
  isPending?: boolean;
  parts?: MessagePart[];
  startedAt?: number;
  completedAt?: number;
  status?: "pending" | "running" | "complete" | "error" | "cancelled";
  error?: string;
}) {
  // Live elapsed time while running
  const [liveElapsed, setLiveElapsed] = useState<string | null>(null);

  useEffect(() => {
    if (!startedAt || completedAt) {
      setLiveElapsed(null);
      return;
    }

    setLiveElapsed(getElapsedTime(startedAt, completedAt));

    const interval = setInterval(() => {
      setLiveElapsed(getElapsedTime(startedAt, completedAt));
    }, 1000);

    return () => clearInterval(interval);
  }, [startedAt, completedAt]);

  const elapsed = completedAt
    ? getElapsedTime(startedAt, completedAt)
    : liveElapsed;

  const effectiveStatus =
    status || (isPending ? "running" : success ? "complete" : "error");

  const formattedAgentName = agent_name
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(" ");

  const panelStatus: CollapsibleStatus =
    effectiveStatus === "running"
      ? "loading"
      : effectiveStatus === "complete"
        ? "success"
        : effectiveStatus === "error"
          ? "error"
          : effectiveStatus === "cancelled"
            ? "cancelled"
            : "idle";

  const panelKey = `subagent-${agent_id}`;

  // Keep sidebar panel data in sync
  useEffect(() => {
    setSubagentPanelData({
      agentId: agent_id,
      agentName: agent_name,
      input,
      result,
      success,
      error,
      isPending,
      parts,
      startedAt,
      completedAt,
      status: effectiveStatus as SubagentPanelData["status"],
    });

    // Auto-open panel on first render when running
    if (effectiveStatus === "running" && !isPersistentToolPanelOpen(panelKey)) {
      openPersistentToolPanel({
        title: formattedAgentName,
        icon: <Users size={16} />,
        status: panelStatus,
        subtitle: elapsed || undefined,
        panelKey,
        children: <SubagentPanelContent agentId={agent_id} />,
      });
    }

    // Keep panel status/elapsed in sync
    if (isPersistentToolPanelOpen(panelKey)) {
      updatePersistentToolPanel(
        (prev) => ({
          ...prev,
          status: panelStatus,
          subtitle: elapsed || undefined,
        }),
        panelKey,
      );
    }
  }, [
    agent_id,
    agent_name,
    input,
    result,
    success,
    error,
    isPending,
    parts,
    startedAt,
    completedAt,
    effectiveStatus,
    panelStatus,
    elapsed,
    formattedAgentName,
    panelKey,
  ]);

  useEffect(() => {
    return () => {
      subagentDataStore.delete(agent_id);
    };
  }, [agent_id]);

  const handleOpenInPanel = useCallback(() => {
    openPersistentToolPanel({
      title: formattedAgentName,
      icon: <Users size={16} />,
      status: panelStatus,
      subtitle: elapsed || undefined,
      panelKey,
      children: <SubagentPanelContent agentId={agent_id} />,
    });
  }, [formattedAgentName, panelStatus, elapsed, panelKey, agent_id]);

  return (
    <div
      className={clsx(
        "my-1.5 rounded-xl overflow-hidden min-w-0 group",
        "border transition-all duration-200",
        effectiveStatus === "running" &&
          "border-blue-200/60 dark:border-blue-800/40 bg-gradient-to-r from-blue-50/60 to-transparent dark:from-blue-950/20",
        effectiveStatus === "complete" &&
          "border-stone-200/60 dark:border-stone-700/40 bg-stone-50/50 dark:bg-stone-800/30",
        effectiveStatus === "error" &&
          "border-red-200/60 dark:border-red-900/40 bg-gradient-to-r from-red-50/60 to-transparent dark:from-red-950/20",
        effectiveStatus === "cancelled" &&
          "border-amber-200/60 dark:border-amber-900/40 bg-gradient-to-r from-amber-50/60 to-transparent dark:from-amber-950/20",
        (!effectiveStatus || effectiveStatus === "pending") &&
          "border-stone-200/60 dark:border-stone-700/40",
      )}
    >
      <div
        className="flex items-center gap-3 px-3.5 py-2.5 cursor-pointer transition-colors hover:bg-white/60 dark:hover:bg-white/5"
        onClick={handleOpenInPanel}
      >
        <div
          className={clsx(
            "flex h-7 w-7 items-center justify-center rounded-lg shrink-0",
            effectiveStatus === "running" && "bg-blue-500/10",
            effectiveStatus === "complete" && "bg-emerald-500/10",
            effectiveStatus === "error" && "bg-red-500/10",
            effectiveStatus === "cancelled" && "bg-amber-500/10",
            (!effectiveStatus || effectiveStatus === "pending") &&
              "bg-stone-500/10",
          )}
        >
          {effectiveStatus === "running" ? (
            <Loader2
              size={13}
              className="text-blue-500 dark:text-blue-400 animate-spin"
            />
          ) : effectiveStatus === "complete" ? (
            <CheckCircle
              size={13}
              className="text-emerald-500 dark:text-emerald-400"
            />
          ) : effectiveStatus === "error" ? (
            <XCircle size={13} className="text-red-500 dark:text-red-400" />
          ) : effectiveStatus === "cancelled" ? (
            <Ban size={13} className="text-amber-500 dark:text-amber-400" />
          ) : (
            <ChevronRight
              size={13}
              className="text-stone-400 dark:text-stone-500"
            />
          )}
        </div>

        <div className="flex-1 min-w-0">
          <span
            className={clsx(
              "text-[13px] font-medium truncate block",
              effectiveStatus === "running" &&
                "text-blue-700 dark:text-blue-300",
              effectiveStatus === "complete" &&
                "text-stone-700 dark:text-stone-300",
              effectiveStatus === "error" && "text-red-700 dark:text-red-300",
              effectiveStatus === "cancelled" &&
                "text-amber-700 dark:text-amber-300",
              (!effectiveStatus || effectiveStatus === "pending") &&
                "text-stone-600 dark:text-stone-400",
            )}
          >
            {formattedAgentName}
          </span>
          {input && (
            <p className="text-[11px] text-stone-400 dark:text-stone-500 truncate mt-px">
              {input}
            </p>
          )}
        </div>

        {elapsed && (
          <span
            className={clsx(
              "text-[11px] shrink-0 tabular-nums tracking-tight px-1.5 py-0.5 rounded-md",
              effectiveStatus === "running" &&
                "text-blue-400 dark:text-blue-500 bg-blue-500/5",
              effectiveStatus === "complete" &&
                "text-stone-400 dark:text-stone-500 bg-stone-500/5",
              effectiveStatus === "error" &&
                "text-red-400 dark:text-red-500 bg-red-500/5",
            )}
          >
            {elapsed}
          </span>
        )}

        <div
          className={clsx(
            "flex items-center justify-center w-6 h-6 rounded-md shrink-0 transition-colors",
            "text-stone-300 dark:text-stone-600 group-hover:text-stone-500 dark:group-hover:text-stone-400",
            "group-hover:bg-stone-100 dark:group-hover:bg-stone-700/50",
          )}
        >
          <PanelRight size={13} />
        </div>
      </div>
    </div>
  );
}

// Sandbox status block component
export function SandboxItem({
  status,
  sandboxId,
  error,
}: {
  status: "starting" | "ready" | "error" | "cancelled";
  sandboxId?: string;
  error?: string;
}) {
  const { t } = useTranslation();
  const [isExpanded, setIsExpanded] = useState(false);

  const hasDetails =
    (status === "ready" && sandboxId) ||
    (status === "error" && error) ||
    status === "cancelled";

  const pillStatus: CollapsibleStatus =
    status === "starting"
      ? "loading"
      : status === "ready"
        ? "success"
        : status === "cancelled"
          ? "cancelled"
          : "error";

  return (
    <CollapsiblePill
      status={pillStatus}
      icon={<Box size={12} className="shrink-0 opacity-50" />}
      label={t("chat.sandbox.name")}
      expandable={!!hasDetails}
      onExpandChange={setIsExpanded}
    >
      {isExpanded && hasDetails && (
        <div className="mt-1 ml-4 pl-3 border-l-2 border-stone-300 dark:border-stone-600 max-h-40 overflow-y-auto">
          {status === "ready" && sandboxId && (
            <div className="text-xs text-stone-600 dark:text-stone-300 pl-1 py-1 font-mono">
              ID: {sandboxId}
            </div>
          )}
          {status === "error" && error && (
            <div className="text-xs text-red-600 dark:text-red-400 pl-1 py-1">
              {error}
            </div>
          )}
          {status === "cancelled" && (
            <div className="text-xs text-amber-600 dark:text-amber-400 pl-1 py-1">
              {t("chat.cancelled")}
            </div>
          )}
        </div>
      )}
    </CollapsiblePill>
  );
}

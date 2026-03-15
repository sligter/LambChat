/**
 * Channels Page - Lists all available channels and their configurations
 */

import { useState, useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Loader2, MessageCircle, Radio } from "lucide-react";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { channelApi } from "../../services/api/channel";
import { ChannelPanel } from "../panels/ChannelPanel";
import { PanelHeader } from "../common/PanelHeader";
import type {
  ChannelMetadata,
  ChannelConfigStatus,
  ChannelType,
} from "../../types/channel";

// Icon map for channel icons
const CHANNEL_ICONS: Record<string, React.FC<{ className?: string }>> = {
  "message-circle": MessageCircle,
  feishu: Radio,
};

// Get icon component
function getChannelIcon(iconName: string, className?: string) {
  const IconComponent = CHANNEL_ICONS[iconName] || MessageCircle;
  return <IconComponent className={className} />;
}

export function ChannelsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { channelType: selectedChannel } = useParams<{
    channelType?: string;
  }>();

  const [channelTypes, setChannelTypes] = useState<ChannelMetadata[]>([]);
  const [statuses, setStatuses] = useState<Record<string, ChannelConfigStatus>>(
    {},
  );
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadData = async () => {
    setIsLoading(true);
    try {
      const types = await channelApi.getTypes();
      setChannelTypes(types);

      // Load status for each channel type
      const statusPromises = types.map(async (ct) => {
        try {
          const status = await channelApi.getStatus(
            ct.channel_type as ChannelType,
          );
          return [ct.channel_type, status] as const;
        } catch {
          return [ct.channel_type, null] as const;
        }
      });

      const statusResults = await Promise.all(statusPromises);
      const statusMap: Record<string, ChannelConfigStatus> = {};
      statusResults.forEach(([type, status]) => {
        if (status) {
          statusMap[type] = status;
        }
      });
      setStatuses(statusMap);
    } catch (error) {
      console.error("Failed to load channel types:", error);
      toast.error(
        t("channel.loadTypesError", "Failed to load available channels"),
      );
    } finally {
      setIsLoading(false);
    }
  };

  // If a specific channel is selected, show the panel
  if (selectedChannel) {
    const metadata = channelTypes.find(
      (ct) => ct.channel_type === selectedChannel,
    );
    if (metadata) {
      return (
        <ChannelPanel
          channelType={selectedChannel as ChannelType}
          metadata={metadata}
        />
      );
    }
  }

  // Show channel list
  return (
    <div className="flex h-full flex-col bg-stone-50 dark:bg-stone-950">
      {/* Header */}
      <PanelHeader
        title={t("channel.title", "Channels")}
        subtitle={t(
          "channel.description",
          "Connect your favorite chat platforms to LambChat",
        )}
        icon={
          <Radio size={18} className="text-stone-600 dark:text-stone-400" />
        }
      />

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-4 py-4 sm:px-6 lg:px-8">
        {isLoading ? (
          <div className="flex h-64 items-center justify-center">
            <div className="flex flex-col items-center gap-3">
              <div className="relative">
                <div className="absolute inset-0 animate-ping rounded-full bg-stone-400/20" />
                <Loader2 className="relative h-10 w-10 animate-spin text-stone-600 dark:text-stone-400" />
              </div>
              <p className="text-sm text-stone-500 dark:text-stone-400">
                {t("common.loading", "Loading...")}
              </p>
            </div>
          </div>
        ) : (
          <div className="mx-auto max-w-full">
            {channelTypes.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-center xl:py-20 2xl:py-24">
                <div className="relative">
                  <div className="absolute inset-0 rounded-full bg-stone-300/20 blur-xl dark:bg-stone-600/20" />
                  <div className="relative flex h-20 w-20 items-center justify-center rounded-full bg-gradient-to-br from-stone-100 to-stone-200 dark:from-stone-800 dark:to-stone-700">
                    <Radio className="h-10 w-10 text-stone-400 dark:text-stone-500" />
                  </div>
                </div>
                <h3 className="mt-6 text-xl font-semibold text-stone-900 dark:text-stone-100">
                  {t("channel.noChannels", "No channels available")}
                </h3>
                <p className="mt-2 max-w-md text-sm text-stone-500 dark:text-stone-400">
                  {t(
                    "channel.noChannelsDesc",
                    "Check back later for available integrations",
                  )}
                </p>
              </div>
            ) : (
              <div className="space-y-3 p-3 sm:p-4">
                {channelTypes.map((ct) => {
                  const status = statuses[ct.channel_type];
                  const isSelected = selectedChannel === ct.channel_type;

                  return (
                    <div
                      key={ct.channel_type}
                      onClick={() => navigate(`/channels/${ct.channel_type}`)}
                      className={`panel-card transition-opacity cursor-pointer ${
                        !status?.enabled ? "opacity-60" : ""
                      } ${
                        isSelected
                          ? "ring-2 ring-stone-400 dark:ring-stone-600"
                          : ""
                      }`}
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex-1 min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            {getChannelIcon(
                              ct.icon,
                              "text-stone-400 dark:text-stone-500 flex-shrink-0",
                            )}
                            <h4 className="font-medium text-stone-900 dark:text-stone-100 truncate">
                              {ct.display_name}
                            </h4>
                            {/* Capabilities badges */}
                            {ct.capabilities.includes("websocket") && (
                              <span className="rounded-full bg-stone-100 px-2 py-0.5 text-xs font-medium text-stone-600 dark:bg-stone-800 dark:text-stone-300">
                                WS
                              </span>
                            )}
                            {ct.capabilities.includes("webhook") && (
                              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700 dark:bg-amber-900/50 dark:text-amber-300">
                                Hook
                              </span>
                            )}
                            {status?.enabled &&
                              (status.connected ? (
                                <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700 dark:bg-green-900/50 dark:text-green-300">
                                  Connected
                                </span>
                              ) : (
                                <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700 dark:bg-amber-900/50 dark:text-amber-300">
                                  Disconnected
                                </span>
                              ))}
                            {!status?.enabled && (
                              <span className="rounded-full bg-stone-100 px-2 py-0.5 text-xs text-stone-500 dark:bg-stone-800 dark:text-stone-500">
                                Not configured
                              </span>
                            )}
                          </div>
                          <p className="mt-2 text-sm text-stone-600 dark:text-stone-400">
                            {ct.description}
                          </p>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

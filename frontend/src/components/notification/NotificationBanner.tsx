import { useEffect, useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";
import { notificationApi } from "../../services/api/notification";
import type { Notification } from "../../types/notification";

export function NotificationBanner() {
  const { i18n } = useTranslation();
  const [notification, setNotification] = useState<Notification | null>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    notificationApi.getActive().then((n) => {
      if (n) {
        setNotification(n);
        setVisible(true);
      }
    });
  }, []);

  const handleDismiss = useCallback(async () => {
    if (!notification) return;
    setVisible(false);
    try {
      await notificationApi.dismiss(notification.id);
    } catch {
      // silently fail - already hidden
    }
  }, [notification]);

  if (!notification || !visible) return null;

  const lang = (i18n.language?.split("-")[0] ||
    "en") as keyof typeof notification.title_i18n;
  const title = notification.title_i18n[lang] || notification.title_i18n.en;
  const content =
    notification.content_i18n[lang] || notification.content_i18n.en;

  return (
    <div className="shrink-0 bg-[var(--theme-primary)] text-white px-4 py-2.5 flex items-center gap-3">
      <div className="flex-1 min-w-0 text-sm">
        <span className="font-medium">{title}</span>
        {content && <span className="ml-2 opacity-90">{content}</span>}
      </div>
      <button
        onClick={handleDismiss}
        className="shrink-0 p-1 rounded-md hover:bg-white/20 transition-colors"
      >
        <X size={16} />
      </button>
    </div>
  );
}

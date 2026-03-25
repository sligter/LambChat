import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { APP_NAME } from "../constants";

const DEFAULT_DESCRIPTION =
  "A pluggable, multi-tenant AI conversation system. Skills + MCP dual-engine driven, modular by design.";

function setMetaDescription(content: string) {
  const selectors = [
    'meta[name="description"]',
    'meta[property="og:description"]',
    'meta[name="twitter:description"]',
  ];
  selectors.forEach((selector) => {
    const el = document.querySelector(selector);
    if (el) el.setAttribute("content", content);
  });
}

/**
 * 设置页面标题和描述的 Hook，支持 i18n
 * @param title 页面标题，可以是翻译 key 或直接字符串
 * @param suffix 标题后缀，默认 "LambChat"
 * @param options i18n 选项
 */
export function usePageTitle(
  title: string,
  suffix: string = APP_NAME,
  options?: { isI18nKey?: boolean; description?: string },
) {
  const { t } = useTranslation();
  const isI18nKey = options?.isI18nKey ?? true;
  const description = options?.description;

  useEffect(() => {
    const translatedTitle = isI18nKey && title ? t(title) : title;
    const translatedSuffix = isI18nKey ? t("appName") || suffix : suffix;

    const fullTitle = translatedTitle
      ? `${translatedTitle} - ${translatedSuffix}`
      : translatedSuffix;
    document.title = fullTitle;

    const desc = description && (isI18nKey ? t(description) : description);
    if (desc) {
      setMetaDescription(desc);
    }

    return () => {
      document.title = isI18nKey ? t("appName") || suffix : suffix;
      setMetaDescription(DEFAULT_DESCRIPTION);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [title, suffix, isI18nKey, description]);
}

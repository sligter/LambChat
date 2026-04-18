import React from "react";

export function RouteLoadingShell() {
  return React.createElement(
    "div",
    {
      className: "flex min-h-[100dvh] items-center justify-center px-6 py-12",
      style: { backgroundColor: "var(--theme-bg)" },
    },
    React.createElement(
      "div",
      {
        className:
          "w-full max-w-md rounded-3xl border px-6 py-7 shadow-sm animate-pulse",
        style: {
          backgroundColor: "var(--theme-bg-card)",
          borderColor: "var(--theme-border)",
        },
      },
      React.createElement("div", {
        className: "mb-5 h-4 w-32 rounded-full",
        style: { backgroundColor: "var(--theme-border)" },
      }),
      React.createElement(
        "p",
        {
          className: "text-sm font-medium",
          style: { color: "var(--theme-text)" },
        },
        "Loading workspace...",
      ),
      React.createElement(
        "div",
        { className: "mt-5 space-y-3" },
        React.createElement("div", {
          className: "h-3 w-full rounded-full",
          style: { backgroundColor: "var(--theme-border)" },
        }),
        React.createElement("div", {
          className: "h-3 w-5/6 rounded-full",
          style: { backgroundColor: "var(--theme-border)" },
        }),
        React.createElement("div", {
          className: "h-3 w-2/3 rounded-full",
          style: { backgroundColor: "var(--theme-border)" },
        }),
      ),
    ),
  );
}

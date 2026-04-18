import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { RouteLoadingShell } from "./RouteLoadingShell.ts";

test("renders a visible loading shell instead of an empty suspense fallback", () => {
  const markup = renderToStaticMarkup(React.createElement(RouteLoadingShell));

  assert.match(markup, /Loading workspace/i);
  assert.match(markup, /animate-pulse/);
});

import test from "node:test";
import assert from "node:assert/strict";
import {
  getKeyboardInsetPx,
  keepElementVisibleInViewport,
  resizeTextareaForContent,
} from "./chatInputViewport.ts";

test("resizeTextareaForContent keeps the newest typed content visible", () => {
  const textarea = {
    style: { height: "" },
    scrollHeight: 420,
    scrollTop: 0,
  };

  resizeTextareaForContent(textarea, 250);

  assert.equal(textarea.style.height, "250px");
  assert.equal(textarea.scrollTop, 420);
});

test("getKeyboardInsetPx returns the overlay height when mobile keyboard covers the bottom", () => {
  assert.equal(
    getKeyboardInsetPx({
      windowHeight: 800,
      viewport: { height: 500, offsetTop: 0 },
    }),
    300,
  );
});

test("getKeyboardInsetPx ignores small browser chrome viewport changes", () => {
  assert.equal(
    getKeyboardInsetPx({
      windowHeight: 800,
      viewport: { height: 760, offsetTop: 0 },
    }),
    0,
  );
});

test("keepElementVisibleInViewport scrolls the input into view when keyboard overlaps it", () => {
  let scrolled = false;
  const element = {
    getBoundingClientRect: () => ({ top: 460, bottom: 540 }),
    scrollIntoView: () => {
      scrolled = true;
    },
  };

  const changed = keepElementVisibleInViewport({
    element,
    viewport: { height: 500, offsetTop: 0 },
  });

  assert.equal(changed, true);
  assert.equal(scrolled, true);
});

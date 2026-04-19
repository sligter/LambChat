import assert from "node:assert/strict";
import test from "node:test";
import type { Message } from "../../types";
import { handleStreamEvent } from "./eventHandlers.ts";
import type { EventHandlerContext } from "./eventHandlers.ts";
import type { StreamEvent } from "./types.ts";

function createContext(
  messages: Message[],
  lastHistoryTimestamp: Date | null,
): EventHandlerContext & { setMessagesCalls: () => number } {
  let setMessagesCalls = 0;

  return {
    sessionIdRef: { current: "session-1" },
    processedEventIdsRef: { current: new Set<string>() },
    lastHistoryTimestampRef: { current: lastHistoryTimestamp },
    activeSubagentStackRef: { current: [] },
    streamVersionRef: { current: 0 },
    setSessionId: () => undefined,
    setMessages: (updater: React.SetStateAction<Message[]>) => {
      setMessagesCalls += 1;
      if (typeof updater === "function") {
        updater(messages);
      }
    },
    setConnectionStatus: () => undefined,
    setIsInitializingSandbox: () => undefined,
    setSandboxError: () => undefined,
    setMessagesCalls: () => setMessagesCalls,
  };
}

test("skips replayed SSE events at the history timestamp boundary", () => {
  const timestamp = "2026-04-19T01:02:03.456Z";
  const ctx = createContext(
    [
      {
        id: "assistant-1",
        role: "assistant",
        content: "",
        timestamp: new Date(timestamp),
        parts: [],
        isStreaming: true,
      },
    ],
    new Date(timestamp),
  );

  const event: StreamEvent = {
    event: "message:chunk",
    data: JSON.stringify({ content: "duplicate", _timestamp: timestamp }),
  };

  handleStreamEvent(event, "assistant-1", "redis-event-1", timestamp, ctx);

  assert.equal(ctx.setMessagesCalls(), 0);
});

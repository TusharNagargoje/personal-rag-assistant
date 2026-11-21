import test from "node:test";
import assert from "node:assert/strict";
import { parseSseFrame, splitSseFrames } from "../lib/sse.mjs";

test("SSE frames can be split across network chunks", () => {
  const first = splitSseFrames("", 'data: {"type":"token","text":"hel');
  assert.deepEqual(first.frames, []);
  const second = splitSseFrames(first.remainder, 'lo"}\n\ndata: [DONE]\n\n');
  assert.equal(second.frames.length, 2);
  assert.deepEqual(parseSseFrame(second.frames[0]), { type: "token", text: "hello" });
  assert.equal(parseSseFrame(second.frames[1]), null);
});

test("SSE parser accepts CRLF and ignores comment lines", () => {
  const result = parseSseFrame(': keepalive\r\ndata: {"type":"done","message_id":"m1","citations":[]}');
  assert.equal(result.type, "done");
  assert.equal(result.message_id, "m1");
});

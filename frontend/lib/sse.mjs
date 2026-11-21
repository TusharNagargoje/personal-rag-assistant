/** Split arbitrarily chunked SSE text into complete blank-line-delimited frames. */
export function splitSseFrames(buffer, incoming) {
  const normalized = `${buffer}${incoming}`.replace(/\r\n/g, "\n");
  const frames = normalized.split("\n\n");
  return { frames: frames.slice(0, -1), remainder: frames.at(-1) ?? "" };
}

/** Parse a server-sent event frame with JSON in its data field. */
export function parseSseFrame(frame) {
  const data = frame
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trimStart())
    .join("\n");
  if (!data || data === "[DONE]") return null;
  return JSON.parse(data);
}

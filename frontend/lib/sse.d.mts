export type StreamEvent =
  | { type: "token"; text: string }
  | { type: "done"; message_id: string; citations: Array<Record<string, unknown>> }
  | { type: "error"; message: string };
export function splitSseFrames(buffer: string, incoming: string): { frames: string[]; remainder: string };
export function parseSseFrame(frame: string): StreamEvent | null;

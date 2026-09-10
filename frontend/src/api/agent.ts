// API Chat
import type { AgentEvent, ChatResponse } from '../types/agent';
import { apiFetch } from './base';

export async function sendChatMessage(
  userId: string,
  threadId: string,
  message: string
): Promise<ChatResponse> {
  return apiFetch<ChatResponse>('/api/chat', {
    method: 'POST',
    body: JSON.stringify({
      user_id: userId,
      thread_id: threadId,
      message,
    }),
  });
}

/**
 * Stream SSE d'un run agent : événements réels du pipeline
 * (RUN_START, STATE_LOAD, USER_MESSAGE, ASSISTANT_MESSAGE,
 *  CHECKPOINT_SAVED, RUN_END).
 * Les événements TOOL_* arrivent via le bus global (events.ts).
 */
export async function streamChatMessage(
  userId: string,
  threadId: string,
  message: string,
  onEvent: (event: AgentEvent) => void
): Promise<void> {
  const params = new URLSearchParams({
    user_id: userId,
    thread_id: threadId,
    message,
  });

  const res = await fetch(`/api/chat/stream?${params}`, {
    headers: { Accept: 'text/event-stream' },
  });

  if (!res.ok || !res.body) {
    // Fallback : mode non-stream
    const result = await sendChatMessage(userId, threadId, message);
    onEvent({
      timestamp: new Date().toISOString(),
      level: 'INFO',
      event: 'ASSISTANT_MESSAGE',
      response: result.response,
      user_id: userId,
      thread_id: threadId,
      interaction_count: result.interaction_count,
    });
    onEvent({
      timestamp: new Date().toISOString(),
      level: 'INFO',
      event: 'RUN_END',
      user_id: userId,
      thread_id: threadId,
    });
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // Parse SSE frames : "event: X\ndata: {...}\n\n"
    const frames = buffer.split('\n\n');
    buffer = frames.pop() ?? '';

    for (const frame of frames) {
      const dataLine = frame
        .split('\n')
        .find((l) => l.startsWith('data:'));
      if (!dataLine) continue;
      try {
        const event = JSON.parse(dataLine.slice(5).trim());
        onEvent(event);
      } catch {
        /* frame non-JSON — ignore */
      }
    }
  }
}

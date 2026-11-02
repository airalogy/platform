import type { InjectionKey } from "vue"
import type { ChatEvent, ChatResponse } from "../utils/api"

export interface RecorderTarget {
  form_id: string
  request_id: string
  version: string
  record_id?: string
  filled: string[]
  last_applied: string[]
  locale: "en-US" | "zh-CN"
}

export interface RecorderProposal {
  form_id: string
  request_id: string
  intent: "fill" | "simulate" | "answer" | "clarify"
  values: Record<string, string | number | boolean>
  skipped: string[]
}

export interface RecorderTurn {
  target: RecorderTarget
  apply: (proposal: RecorderProposal, chatId?: string) => Promise<string>
}

export const recorderTurnKey: InjectionKey<{ begin: (chatId?: string) => RecorderTurn | undefined, enabled: () => boolean }> = Symbol("active-recorder-turn")

// Only process live responses to the originating request, never replay chat history.
export async function* applyRecorderResponse(stream: AsyncGenerator<ChatEvent, ChatResponse, unknown>, turn?: RecorderTurn): AsyncGenerator<ChatEvent, ChatResponse, unknown> {
  let serverId: string | undefined
  try {
    for (;;) {
      const next = await stream.next()
      if (next.done)
        return next.value
      const event = next.value
      if (event.type === "meta")
        serverId = event.data.chat_id
      const message = event.type === "message" && event.data.message
      if (turn && message?.recorder_proposal) {
        const receipt = await turn.apply(message.recorder_proposal, serverId)
        message.content = [message.content, receipt].filter(Boolean).join("\n\n")
      }
      yield event
    }
  }
  finally {
    await stream.return({})
  }
}

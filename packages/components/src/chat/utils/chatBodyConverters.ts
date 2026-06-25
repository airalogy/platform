/* eslint-disable ts/no-non-null-asserted-optional-chain */
import type { ChatMessageItem, CompletionOptions, TextMessagePart } from "../providers/types"
import type { ChatCompletion, ChatCompletionAssistantMessageParam, ChatCompletionChunk, ChatCompletionCreateParams, ChatCompletionMessageParam } from "./openai.d.ts"

export function toChatMessage(
  message: ChatMessageItem,
): ChatCompletionMessageParam {
  if (message.role === "tool") {
    return {
      role: "tool",
      content: message.content,
      tool_call_id: message.toolCallId,
    }
  }
  if (message.role === "system") {
    return {
      role: "system",
      content: message.content,
    }
  }

  if (message.role === "assistant") {
    const msg: ChatCompletionAssistantMessageParam = {
      role: "assistant",
      content:
        typeof message.content === "string"
          ? message.content || " " // LM Studio (and other providers) don't accept empty content
          : message.content
            .filter(part => part.type === "text")
            .map(part => part as TextMessagePart), // can remove with newer typescript version
    }

    if (message.toolCalls) {
      msg.tool_calls = message.toolCalls.map(toolCall => ({
        id: toolCall.id!,
        type: toolCall.type!,
        function: {
          name: toolCall.function?.name!,
          arguments: toolCall.function?.arguments!,
        },
      }))
    }
    return msg
  }
  else {
    if (typeof message.content === "string") {
      return {
        role: "user",
        content: message.content ?? " ", // LM Studio (and other providers) don't accept empty content
      }
    }

    // If no multi-media is in the message, just send as text
    // for compatibility with OpenAI-"compatible" servers
    // that don't support multi-media format
    return {
      role: "user",
      content: !message.content.some(item => item.type !== "text")
        ? message.content
          .map(item => (item as TextMessagePart).text)
          .join("") || " "
        : message.content.map((part) => {
          if (part.type === "imageUrl") {
            return {
              type: "image_url" as const,
              image_url: {
                url: part.imageUrl?.url ?? "",
                detail: "auto" as const,
              },
            }
          }
          return part
        }),
    }
  }
}

export function toChatBody(
  messages: ChatMessageItem[],
  options: CompletionOptions,
): ChatCompletionCreateParams {
  const params: ChatCompletionCreateParams = {
    messages: messages.map(toChatMessage),
    model: options.model,
    max_tokens: options.maxTokens,
    temperature: options.temperature,
    top_p: options.topP,
    frequency_penalty: options.frequencyPenalty,
    presence_penalty: options.presencePenalty,
    stream: options.stream ?? true,
    stop: options.stop,
    // prediction: options.prediction,
    tool_choice: options.toolChoice,
  }

  if (options.tools?.length) {
    params.tools = options.tools.map(tool => ({
      type: tool.type,
      function: {
        name: tool.function.name,
        description: tool.function.description,
        parameters: tool.function.parameters,
        strict: tool.function.strict,
      },
    }))
  }

  return params
}

export function toCompleteBody(
  prompt: string,
  options: CompletionOptions,
): ChatCompletionCreateParams {
  return {
    // prompt,
    messages: [{ role: "user", content: prompt }],
    model: options.model,
    max_tokens: options.maxTokens,
    temperature: options.temperature,
    top_p: options.topP,
    frequency_penalty: options.frequencyPenalty,
    presence_penalty: options.presencePenalty,
    stream: options.stream ?? true,
    stop: options.stop,
  }
}

export function fromChatResponse(response: ChatCompletion): ChatMessageItem {
  const message = response.choices[0].message
  const toolCall = message.tool_calls?.[0]
  if (toolCall) {
    return {
      role: "assistant",
      content: "",
      toolCalls: message.tool_calls,
    }
  }

  return {
    role: "assistant",
    content: message.content ?? "",
  }
}

export function fromChatCompletionChunk(
  chunk: ChatCompletionChunk,
): ChatMessageItem | undefined {
  const delta = chunk.choices?.[0]?.delta

  if (delta?.content) {
    return {
      role: "assistant",
      content: delta.content,
    }
  }
  else if (delta?.tool_calls) {
    return {
      role: "assistant",
      content: "",
      toolCalls: delta?.tool_calls.map((tool_call: any) => ({
        id: tool_call.id,
        type: tool_call.type,
        function: {
          name: tool_call.function.name,
          arguments: tool_call.function.arguments,
        },
      })),
    }
  }

  return undefined
}

export type LlmApiRequestType =
  | "chat"
  | "streamChat"
  | "complete"
  | "streamComplete"
  | "streamFim"
  | "embed"
  | "rerank"
  | "list"

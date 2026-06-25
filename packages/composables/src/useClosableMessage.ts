import type { MessageOptions, MessageType } from "naive-ui"
import type { MessageApiInjection, MessageReactive } from "naive-ui/es/message/src/MessageProvider"
import type { VNodeChild } from "vue"
import { useMessage } from "naive-ui"
import { nanoid } from "nanoid"
import { h } from "vue"

type MessageContent = string | (() => VNodeChild)

export function renderMessageContent(content: MessageContent): MessageContent {
  if (typeof content === "string") {
    const lines = content.split("\n")
    if (lines.length > 1) {
      return () => h(
        "div",
        lines.map((line, index) =>
          [h("pre", { style: { margin: 0, display: "inline", fontFamily: "inherit", whiteSpace: "pre-wrap" }, key: index }, line), h("br")],
        ).flat(),
      )
    }
  }
  return content
}
type ContentType = string | (() => VNodeChild)
interface PrivateMessageRef extends MessageReactive {
  key: string
  hide?: () => void
}

export function useClosableMessage(options?: { max?: number }): MessageApiInjection {
  let message = (window as unknown as { $message: MessageApiInjection }).$message
  if (!message) {
    try {
      message = useMessage()
    }
    catch (error) {
      const { max } = options || { max: 10 }
      const messageListRef = ref<PrivateMessageRef[]>([])
      const messageRefs = ref<Record<string, PrivateMessageRef>>({})
      const api: MessageApiInjection = {
        create(content: ContentType, options?: MessageOptions) {
          return create(content, { type: "default", ...options })
        },
        info(content: ContentType, options?: MessageOptions) {
          return create(content, { ...options, type: "info" })
        },
        success(content: ContentType, options?: MessageOptions) {
          return create(content, { ...options, type: "success" })
        },
        warning(content: ContentType, options?: MessageOptions) {
          return create(content, { ...options, type: "warning" })
        },
        error(content: ContentType, options?: MessageOptions) {
          return create(content, { ...options, type: "error" })
        },
        loading(content: ContentType, options?: MessageOptions) {
          return create(content, { ...options, type: "loading" })
        },
        destroyAll,
      }

      function create(
        content: ContentType,
        options: MessageOptions & { type: MessageType },
      ): MessageReactive {
        const key = nanoid()
        const messageReactive = reactive<PrivateMessageRef>({
          ...options,
          content,
          key,
          destroy: () => {
            messageRefs.value[key]?.hide?.()
          },
        })
        if (max && messageListRef.value.length >= max) {
          messageListRef.value.shift()
        }
        messageListRef.value.push(messageReactive)
        return messageReactive
      }
      // function handleAfterLeave(key: string): void {
      //   messageListRef.value.splice(
      //     messageListRef.value.findIndex(message => message.key === key),
      //     1,
      //   )
      //   delete messageRefs.value[key]
      // }
      function destroyAll(): void {
        Object.values(messageRefs.value).forEach((messageInstRef) => {
          messageInstRef?.hide?.()
        })
      }

      return api
    }
  }

  return {
    ...message,
    error: (content, options) =>
      message.error(renderMessageContent(content), { closable: true, duration: 8000, ...options }),
    success: (content, options) =>
      message.success(renderMessageContent(content), options),
    warning: (content, options) =>
      message.warning(renderMessageContent(content), options),
    info: (content, options) =>
      message.info(renderMessageContent(content), options),
  }
}

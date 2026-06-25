import type { MentionNodeAttrs } from "@airalogy/components/markdown-editor/extensions/mention"
import type { JSONContent } from "@tiptap/vue-3"
import type { UseEventBusReturn } from "@vueuse/core"
import type { ContextItemWithId, MessageContent, MessagePart, RangeInFile, TextMessagePart } from "../providers/types"

import { requestWithEventBus } from "@airalogy/composables"

export interface ResolveContextItemPayload {
  name?: string
  query?: string
  fullInput?: string
  selectedCode?: RangeInFile[]
}

/**
 * This function converts the input from the editor to a string, resolving any context items
 * Context items are appended to the top of the prompt and then referenced within the input
 * @param editor
 * @returns string representation of the input
 */

async function resolveEditorContent(
  editorState: JSONContent,
  eventBus: UseEventBusReturn<"refreshSubmenuItems" | "updateSubmenuItems" | "request:context/getContextItems" | "response:context/getContextItems" | "request:context/loadSubmenuItems" | "response:context/loadSubmenuItems", any>,
): Promise<[ContextItemWithId[], RangeInFile[], MessageContent]> {
  const parts: MessagePart[] = []
  const contextItemAttrs: MentionNodeAttrs[] = []
  const selectedCode: RangeInFile[] = []
  let slashCommand
  if (editorState?.content) {
    for (const p of editorState.content) {
      if (p.type === "paragraph") {
        const [text, ctxItems, foundSlashCommand] = resolveParagraph(p)

        // Only take the first slash command

        if (foundSlashCommand && typeof slashCommand === "undefined") {
          slashCommand = foundSlashCommand
        }

        contextItemAttrs.push(...ctxItems)

        if (text === "") {
          continue
        }

        if (parts[parts.length - 1]?.type === "text") {
          parts[parts.length - 1].text += `\n${text}`
        }
        else {
          parts.push({ type: "text", text })
        }
      }
      else if (p.type === "codeBlock" && p.attrs) {
        if (!p.attrs.item.editing) {
          const text
            = `\`\`\`${p.attrs.item.description
            }\n${p.attrs.item.content
            }\n\`\`\``
          if (parts[parts.length - 1]?.type === "text") {
            parts[parts.length - 1].text += `\n${text}`
          }
          else {
            parts.push({
              type: "text",
              text,
            })
          }
        }

        const name: string = p.attrs.item.name
        let lines = name.substring(name.lastIndexOf("(") + 1)
        lines = lines.substring(0, lines.lastIndexOf(")"))
        const [start, end] = lines.split("-")

        selectedCode.push({
          filepath: p.attrs.item.description,
          range: {
            start: { line: Number.parseInt(start) - 1, character: 0 },
            end: { line: Number.parseInt(end) - 1, character: 0 },
          },
        })
      }
      else if (p.type === "image" && p.attrs) {
        parts.push({
          type: "imageUrl",
          imageUrl: {
            url: p.attrs.src,
          },
        })
      }
      else {
        console.warn("Unexpected content type", p.type)
      }
    }
  }

  const contextItems: ContextItemWithId[] = []
  // TODO: resolve context items

  for (const item of contextItemAttrs) {
    const data = {
      name: item.itemType === "contextProvider" ? item.id : item.itemType,
      query: item.query,
      fullInput: stripImages(parts),
      selectedCode,
    }

    // await eventBus.emit(
    //   "request:context/getContextItems",
    //   data,
    // )

    // const resolvedItems: ContextItemWithId[] = await new Promise(resolve => eventBus.once((event, payload: ContextItemWithId[]) => {
    //   if (event === "response:context/getContextItems") {
    //     resolve(payload)
    //   }
    // }))
    const result = await requestWithEventBus(eventBus, "request:context/getContextItems", "response:context/getContextItems", data)
    if (result.status === "success") {
      contextItems.push(...result.content)
    }
    else {
      console.error("Failed to resolve context items", result.error)
    }
  }

  if (slashCommand) {
    const lastTextIndex = findLastIndex(parts, part => part.type === "text")
    const lastPart = `${slashCommand} ${parts[lastTextIndex]?.text || ""}`
    if (parts.length > 0) {
      parts[lastTextIndex].text = lastPart
    }
    else {
      parts.push({ type: "text", text: lastPart })
    }
  }

  return [contextItems, selectedCode, parts]
}

function findLastIndex<T>(
  array: T[],
  predicate: (value: T, index: number, obj: T[]) => boolean,
): number {
  for (let i = array.length - 1; i >= 0; i--) {
    if (predicate(array[i], i, array)) {
      return i
    }
  }
  return -1 // if no element satisfies the predicate
}

function resolveParagraph(p: JSONContent): [string, MentionNodeAttrs[], string | undefined] {
  let text = ""
  const contextItems: MentionNodeAttrs[] = []

  let slashCommand: string | undefined
  if (p.content) {
    for (const child of p.content) {
      if (!child) {
        continue
      }

      if (child.type === "text") {
        if (!child.text) {
          continue
        }

        text += text === "" ? child.text.trimStart() : child.text
      }
      else if (child.type === "mention" && child.attrs) {
        text
          += typeof child.attrs.renderInlineAs === "string"
            ? child.attrs.renderInlineAs
            : child.attrs.label
        contextItems.push(child.attrs as MentionNodeAttrs)
      }
      else if (child.type === "slashcommand" && child.attrs) {
        if (typeof slashCommand === "undefined") {
          slashCommand = child.attrs.id
        }
        else {
          text += child.attrs.label
        }
      }
      else {
        console.warn("Unexpected child type", child.type)
      }
    }
  }
  return [text, contextItems, slashCommand]
}

export default resolveEditorContent

export function stripImages(messageContent: MessageContent) {
  if (typeof messageContent === "string") {
    return messageContent
  }
  return messageContent
    .filter(part => part.type === "text")
    .map(part => (part as TextMessagePart).text)
    .join("\n")
}

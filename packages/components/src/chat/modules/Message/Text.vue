<!-- eslint-disable vue/no-v-html -->
<template>
  <div class="min-w-[20px] w-fit rounded-md p-2 text-wrap" :class="wrapClass">
    <slot name="prefix" />
    <div ref="textRef" class="relative break-words rounded-inherit leading-relaxed">
      <template v-if="editing && editor">
        <editor-content :editor="editor" class="w-full" />
        <div class="mt-2 flex justify-end gap-2">
          <n-button type="primary" size="small" @click="handleSave">
            Submit
          </n-button>
          <n-button type="primary" size="small" secondary plain @click="handleCancel">
            Cancel
          </n-button>
        </div>
        <div class="input__border" />
        <div class="input__state-border" />
      </template>
      <!-- <n-spin v-else :show="!props.text && props.loading" size="small" class="size-full" content-class="size-full min-h-4"> -->

      <template v-else>
        <!-- Thinking content (if exists) - shown before actual content -->
        <thinking-content
          v-if="parsedContent.thinking"
          :thinking-text="parsedContent.thinking"
          :has-actual-content="!!parsedContent.actual"
        />

        <!-- Actual content -->
        <styled-markdown-preview
          v-if="parsedContent.hasThinkTag ? parsedContent.actual : true"
          :source="parsedContent.hasThinkTag ? parsedContent.actual : props.text"
          :loading="props.loading"
          :resolve-file="props.resolveFile"
        />
      </template>
      <!-- </n-spin> -->
    </div>
    <slot name="suffix" />
  </div>
</template>

<script lang="ts" setup>
import { Document, Paragraph, Text } from "@airalogy/components/markdown-editor/extensions"
import StyledMarkdownPreview from "@airalogy/components/markdown-editor/extensions/chat/StyledMarkdownPreview.vue"
import { Editor, EditorContent } from "@tiptap/vue-3"
import ThinkingContent from "./ThinkingContent.vue"

interface Props {
  inversion?: boolean
  error?: boolean
  text?: string
  loading?: boolean
  asRawText?: boolean
  editing?: boolean
  resolveFile?: (id: string) => Promise<{ url: string } | null>
}

const props = withDefaults(defineProps<Props>(), {
  editing: false,
  resolveFile: undefined,
})

const emit = defineEmits<Emits>()
interface Emits {
  (e: "update:editing", value: boolean): void
  (e: "save", text: string): void
}
const textRef = ref<HTMLElement>()
const focusedRef = ref<boolean>(false)
const editor = shallowRef<Editor | null> (null)

/**
 * Parse text to extract thinking content and actual content
 * Handles streaming scenario where closing tag might not exist yet
 */
const parsedContent = computed(() => {
  if (!props.text) {
    return { thinking: "", actual: "", hasThinkTag: false }
  }

  // Check if text contains complete opening <think> tag
  const openTagIndex = props.text.indexOf("<think>")

  if (openTagIndex === -1) {
    // Check if text might be in the middle of typing <think> tag
    // Find the last occurrence of "<" and check if it could be the start of <think>
    const lastLessThan = props.text.lastIndexOf("<")

    if (lastLessThan !== -1) {
      // Get the text after the last "<"
      const textAfterLessThan = props.text.substring(lastLessThan)

      // Check if this could be an incomplete <think> tag
      const possibleIncompleteTag = textAfterLessThan.toLowerCase()
      const thinkTagStart = "<think>"

      // If the text after "<" matches the beginning of "<think>" but isn't complete
      if (thinkTagStart.startsWith(possibleIncompleteTag) && possibleIncompleteTag.length < thinkTagStart.length) {
        // This is an incomplete <think> tag, hide it
        const textWithoutIncomplete = props.text.substring(0, lastLessThan)
        return { thinking: "", actual: textWithoutIncomplete, hasThinkTag: false }
      }
    }

    // No thinking content
    return { thinking: "", actual: props.text, hasThinkTag: false }
  }

  // Check if closing tag exists
  const closeTagIndex = props.text.indexOf("</think>")

  if (closeTagIndex !== -1) {
    // Complete thinking block found
    // Extract thinking content (excluding the closing tag)
    const thinking = props.text.substring(openTagIndex + 7, closeTagIndex).trim()
    const before = props.text.substring(0, openTagIndex).trim()
    const after = props.text.substring(closeTagIndex + 8).trim()
    const actual = [before, after].filter(Boolean).join("\n\n").trim()
    return { thinking, actual, hasThinkTag: true }
  }
  else {
    // Streaming: closing tag not yet received
    // Check if we're in the middle of typing the closing tag
    const textAfterOpen = props.text.substring(openTagIndex + 7)
    const lastLessThan = textAfterOpen.lastIndexOf("</")

    if (lastLessThan !== -1) {
      // Get the text after the last "</"
      const textAfterClosing = textAfterOpen.substring(lastLessThan)
      const closeTagStart = "</think>"

      // If this could be an incomplete closing tag
      if (closeTagStart.startsWith(textAfterClosing.toLowerCase()) && textAfterClosing.length < closeTagStart.length) {
        // This is an incomplete closing tag, don't include it in thinking content
        const thinkingContent = textAfterOpen.substring(0, lastLessThan).trim()
        const actual = props.text.substring(0, openTagIndex).trim()
        return { thinking: thinkingContent, actual, hasThinkTag: true }
      }
    }

    // Everything after <think> is thinking content
    const thinking = textAfterOpen.trim()
    const actual = props.text.substring(0, openTagIndex).trim()
    return { thinking, actual, hasThinkTag: true }
  }
})
watch(() => props.editing, (value) => {
  if (!editor.value && value) {
    editor.value = new Editor({
      content: props.text,
      extensions: [
        Document,
        Paragraph,
        Text,
      ],
      editorProps: {
        attributes: {
          class: "message-input-editor",
        },
      },
      onFocus: () => {
        focusedRef.value = true
      },
      onBlur: () => {
        focusedRef.value = false
      },
    })
  }
  else {
    editor.value?.commands.setContent(props.text || "")
  }
})

const wrapClass = computed(() => {
  const classes: string[] = []
  const { inversion, editing } = props
  if (inversion) {
    if (editing) {
      classes.push("border")
      classes.push("flex-1")
      classes.push("message-wrapper")
      if (focusedRef.value) {
        classes.push("message-wrapper--focused")
      }
    }

    classes.push("bg-[#E9F0FF]")
    classes.push("message-request")
  }
  else {
    classes.push("bg-[#f4f6f8]")
    classes.push("message-reply")
  }

  return classes
})

function handleSave() {
  if (editor.value && !editor.value.isEmpty) {
    emit("save", editor.value.getText())
  }

  emit("update:editing", false)
}

function handleCancel() {
  emit("update:editing", false)
}
</script>

<style lang="sass">
.message-input-editor
  &.ProseMirror-focused
    outline: none

.input__border, .input__state-border
  box-sizing: border-box
  position: absolute
  left: -0.5rem
  right: -0.5rem
  top: -0.5rem
  bottom: -0.5rem
  pointer-events: none
  border-radius: inherit
  border: 1px solid rgb(var(--border-color))
  transition: box-shadow .3s cubic-bezier(.4, 0, .2, 1), border-color .3s cubic-bezier(.4, 0, .2, 1)

.message-wrapper
  &:hover
    .input__state-border
      border-color: rgb(var(--primary-color))
  &--focused
    .input__state-border
      border-color: rgb(var(--primary-color))
      box-shadow: 0 0 0 2px rgba(26, 121, 255, 0.2)
</style>

<template>
  <div
    ref="dropZoneRef" class="tiptap-dropzone tiptap-container tiptap-input-container relative cursor-text rounded-xl p-2"
    :class="{
      'tiptap-container--focus': focusedRef,
      'tiptap-container--empty': editor?.isEmpty,
    }"
    @click="editor?.commands?.focus?.()"
  >
    <!-- Prefix slot -->
    <div class="tiptap-prefix">
      <slot name="fixed-prefix">
        <chat-context-tags :source="props.source" />
        <!-- Add FilePreview component -->
        <file-preview v-if="attachments?.length" :attachments="attachments" class="mt-2" @remove="removeAttachment" />
      </slot>
      <slot name="prefix" />
    </div>

    <!-- Recording/Processing status -->
    <voice-input-status
      :is-recording="isRecording"
      :is-processing="isProcessingAudio"
      :recording-duration="audioRecorder.recordingDuration"
      class-name="my-3"
    />

    <!-- Editor area -->
    <n-scrollbar v-if="!isRecording && !isProcessingAudio" ref="scrollbarRef" class="max-h-[12em] pt-1">
      <!-- FIXME: need implement scrollbar -->
      <editor-content :editor="editor" @wheel="handleScroll" />
    </n-scrollbar>
    <!-- Suffix slot with actions and submit button -->

    <div class="flex items-center gap-1">
      <!-- Left side: Model selector -->
      <slot name="actions">
        <chat-model-selector />
        <chat-model-options />
      </slot>

      <div class="flex-1" />

      <!-- Right side: Voice recorder and send button -->
      <chat-voice-recorder @recording-stopped="handleRecordingStopped" />

      <!-- Default submit button -->
      <slot name="suffix">
        <n-button type="primary" :disabled="buttonDisabled" class="px-3" @click="handleClick">
          <template #icon>
            <n-icon :size="16">
              <icon-shared-stop-message v-if="loading" />
              <icon-shared-send-message v-else />
            </n-icon>
          </template>
        </n-button>
      </slot>
    </div>

    <div v-if="isOverDropZone" class="tiptap-dropzone__overlay">
      <n-icon size="32" class="mb-2">
        <icon-ion-cloud-upload-outline />
      </n-icon>
      <span>{{ $t("chat.dropzoneHint") }}</span>
    </div>
    <div class="input__border" />
    <div class="input__state-border" />
  </div>
</template>

<script setup lang="ts">
import type { AddToChatPayload, BubbleMenuEventName, BubbleMenuEventPayload } from "@airalogy/composables/useBubbleMenu"
import type { Editor, VueRenderer } from "@tiptap/vue-3"
import type { SearchResult } from "minisearch"

import type { SelectOption, UploadFileInfo } from "naive-ui"
import type { ContextItemId, ContextSubmenuItem, ContextSubmenuItemWithProvider } from "../providers/types"
import { requestWithEventBus, useClosableMessage, useMinisearch } from "@airalogy/composables"
import { bubbleMenuEventKey } from "@airalogy/shared/constants/eventKey"
import { ChatType } from "@airalogy/shared/enum/chat.js"
import { $t } from "@airalogy/shared/locales"
import { EditorContent, useEditor } from "@tiptap/vue-3"
import { useDropZone, useEventBus } from "@vueuse/core"
import MiniSearch from "minisearch"
import { NScrollbar } from "naive-ui"

import { nanoid } from "nanoid"
import { Code, Document, HardBreak, Mention, Paragraph, Placeholder, SlashCommand, Text, TiptapHistory } from "../../markdown-editor/extensions"
import { getContextProviderDropdownOptions, getSlashCommandDropdownOptions } from "../../markdown-editor/modules/mention/getSuggestions"
import VoiceInputStatus from "../../voice-input-status.vue"
import { useChatInfoStore } from "../composables/useChatInfoStore"
import ChatContextTags from "./chat-actions/context-tags.vue"
import ChatModelOptions from "./chat-actions/model-options.vue"
import ChatModelSelector from "./chat-actions/model-selector.vue"
import ChatVoiceRecorder from "./chat-actions/voice-recorder.vue"
import FilePreview from "./file-preview.vue"
// import { useAppStore } from "@airalogy/components/store/modules/app"
import { defaultConfig } from "../store/helper"
import resolveEditorContent from "../utils/resolveInput"

interface IProps {
  placeholder?: string
  minHeight?: string
  maxHeight?: string
  loading?: boolean
  submitHandler?: (value: string) => Promise<void> | void
  availableContextProviders?: Chat.ContextProviderDescription[]
  availableSlashCommands?: Chat.ComboBoxItem[]
  contextSelectOptions?: SelectOption[]
  source: Chat.ChatSource
}

const props = withDefaults(defineProps<IProps>(), {
  placeholder: "",
  minHeight: "100px",
  maxHeight: "300px",
  loading: false,
  source: "global",
})

const emit = defineEmits<{
  (e: "update:modelValue", value: string): void
  (e: "submit", value: string): void
  (e: "stop"): void
  (e: "drop:files", files: File[]): void
  (e: "selectContext", value: string): void
  (e: "update:popoverComponent", value: VueRenderer | null): void
  (e: "update:popoverReference", value: HTMLElement | null): void
}>()

const resolvedPlaceholder = computed(() => props.placeholder || $t("chat.placeholder"))

const {
  session,
  loading,
  inputMethod,
  isRecording,
  audioBase64,
  audioRecorder,
  attachments,
  handleSubmit: storeHandleSubmit,
  handleStop,
  removeAttachment,
  handleUpload,
  selectedModel,
  selectedRole,
  prompt,
  resetAudioRecorder,
  sttEndpoint,
  token,
} = useChatInfoStore()! || {}

const isProcessingAudio = ref(false)
const dropZoneRef = ref<HTMLElement | null>(null)
const scrollbarRef = ref<any>(null)
const { isOverDropZone } = useDropZone(dropZoneRef, {
  onDrop: (files) => {
    if (files) {
      emit("drop:files", Array.from(files))
      const fileInfo: UploadFileInfo = {
        file: files[0],
        status: "uploading",
        id: nanoid(),
        name: files[0].name,
      }
      // TODO: implement onError, onProgress, onFinish
      handleUpload({ file: fileInfo as any, onError() {}, onProgress() { }, onFinish() { } })
    }
  },
})

const inSubmenuRef = ref<string | undefined>(undefined)
const inDropdownRef = ref(false)

// const appStore = useAppStore()
// const { popoverComponent, popoverReference } = storeToRefs(appStore)

function onClose() {
  inSubmenuRef.value = undefined
  inDropdownRef.value = false
  emit("update:popoverComponent", null)
  emit("update:popoverReference", null)
}

function onOpen(component: VueRenderer) {
  inDropdownRef.value = true
  emit("update:popoverComponent", component as any)
  emit("update:popoverReference", component.props.decorationNode as HTMLElement)
}

async function onUpdate(props: any) {
  if (props.decorationNode) {
    emit("update:popoverReference", props.decorationNode)
  }
}

const focusedRef = ref(false)

function enterSubmenu(editor: Editor, providerId: string) {
  const contents = editor.getText()
  const indexOfAt = contents.lastIndexOf("@")
  if (indexOfAt === -1) {
    return
  }

  // Find the position of the last @ character
  // We do this because editor.getText() isn't a correct representation including node views
  let startPos = editor.state.selection.anchor
  while (
    startPos > 0
    && editor.state.doc.textBetween(startPos, startPos + 1) !== "@"
  ) {
    startPos--
  }
  startPos++

  editor.commands.deleteRange({
    from: startPos,
    to: editor.state.selection.anchor,
  })
  inSubmenuRef.value = providerId

  // to trigger refresh of suggestions
  editor.commands.insertContent(":")
  editor.commands.deleteRange({
    from: editor.state.selection.anchor - 1,
    to: editor.state.selection.anchor,
  })
}

const MINISEARCH_OPTIONS = {
  prefix: true,
  fuzzy: 2,
}

const MAX_LENGTH = 70

const { minisearches, fallbackResults, setMinisearch, setFallbackResults, setLoaded } = useMinisearch<ContextSubmenuItem | ContextSubmenuItemWithProvider>({
  fallback: [],
  options: {
    fields: ["title", "description"],
    storeFields: ["id", "title", "description"],
  },
})

const submenuBus = useEventBus<"refreshSubmenuItems" | "updateSubmenuItems" | "request:context/getContextItems" | "response:context/getContextItems" | "request:context/loadSubmenuItems" | "response:context/loadSubmenuItems">("submenu-eventbus")
const bubbleMenuEventBus = useEventBus<BubbleMenuEventName, BubbleMenuEventPayload>(bubbleMenuEventKey)

/*
  useWebviewListener("refreshSubmenuItems", async (data) => {
    setLoaded(false);
  });

  useWebviewListener("updateSubmenuItems", async (data) => {
    const minisearch = new MiniSearch<ContextSubmenuItem>({
      fields: ["title", "description"],
      storeFields: ["id", "title", "description"],
    });

    minisearch.addAll(data.submenuItems);

    setMinisearches((prev) => ({ ...prev, [data.provider]: minisearch }));

    if (data.provider === "file") {
      const openFiles = await getOpenFileItems();
      setFallbackResults((prev) => ({
        ...prev,
        file: [
          ...openFiles,
          ...data.submenuItems.slice(0, MAX_LENGTH - openFiles.length),
        ],
      }));
    } else {
      setFallbackResults((prev) => ({
        ...prev,
        [data.provider]: data.submenuItems.slice(0, MAX_LENGTH),
      }));
    }
  });
*/
function getSubmenuSearchResults(providerTitle: string | undefined, query: string): SearchResult[] {
  console.debug(
    "Executing getSubmenuSearchResults. Provider:",
    providerTitle,
    "Query:",
    query,
  )
  const entries = Object.entries(minisearches.value)
  console.debug("Current minisearches:", entries)
  if (providerTitle === undefined) {
    // Return search combined from all providers
    const results = entries.map(([providerTitle, minisearch]) => {
      const results = minisearch.search(
        query,
        MINISEARCH_OPTIONS,
      )
      console.debug(
        `Search results for ${providerTitle}:`,
        results.length,
      )
      return results.map((result) => {
        return { ...result, providerTitle }
      })
    })

    return results.flat().sort((a, b) => b.score - a.score)
  }
  if (!minisearches.value[providerTitle]) {
    console.debug(`No minisearch found for provider: ${providerTitle}`)
    return []
  }

  const results = minisearches.value[providerTitle]
    .search(query, MINISEARCH_OPTIONS)
    .map((result) => {
      return { ...result, providerTitle }
    })
  console.debug(`Search results for ${providerTitle}:`, results.length)

  return results
}

function getSubmenuContextItems(providerTitle: string | undefined, query: string, limit: number = MAX_LENGTH): (ContextSubmenuItem & { providerTitle: string })[] {
  try {
    // 1. Search using minisearch
    let searchResults: (SearchResult & ContextSubmenuItemWithProvider)[] = []

    if (providerTitle === undefined) {
      // Include results from all providers
      searchResults = Object.keys(minisearches.value).flatMap(providerTitle =>
        minisearches.value[providerTitle]
          .search(query, MINISEARCH_OPTIONS)
          .map((result) => {
            return {
              ...result,
              providerTitle,
              title: result.title,
              description: result.description,
            }
          }),
      )
    }
    else {
      // Only include results from the specified provider
      if (minisearches.value[providerTitle]) {
        searchResults = minisearches.value[providerTitle]
          .search(query, MINISEARCH_OPTIONS)
          .map((result) => {
            return {
              ...result,
              providerTitle,
              title: result.title,
              description: result.description,
            }
          })
      }
    }
    searchResults.sort((a, b) => b.score - a.score)

    // 2. Add fallback results if no search results
    if (searchResults.length === 0) {
      const fallbackItems = (
        providerTitle ? (fallbackResults.value[providerTitle] ?? []) : []
      )
        .slice(0, limit)
        .map((result) => {
          return {
            ...result,
            providerTitle: providerTitle || "unknown",
          }
        })

      if (fallbackItems.length === 0) {
        const loadingFiller = [
          {
            id: "loading",
            title: "Loading...",
            description: "Please wait while items are being loaded",
            providerTitle: providerTitle || "unknown",
          },
        ]

        // If getting for all providers
        if (!providerTitle) {
          // then show loading if ANY loading
          if (Object.keys(minisearches.value).length > 0) {
            return loadingFiller
          }
        }
        else {
          // Otherwise just check if the provider is loading
          if (Object.keys(minisearches.value).includes(providerTitle)) {
            return loadingFiller
          }
        }
      }

      return fallbackItems
    }
    const limitedResults = searchResults.slice(0, limit).map((result) => {
      return {
        id: result.id,
        title: result.title,
        description: result.description,
        providerTitle: result.providerTitle,
        label: result.label,
        icon: result.icon,
      }
    })
    return limitedResults
  }
  catch (error) {
    console.error("Error in getSubmenuContextItems:", error)
    return []
  }
}

const availableContextProviders = computed(() => {
  return props.availableContextProviders || (session.value?.config?.contextProviders || defaultConfig.contextProviders).map(provider => provider.description) as Chat.ContextProviderDescription[]
})

const availableSlashCommands = computed(() => {
  return props.availableSlashCommands || session.value?.config?.slashCommands || []
})

const providersLoading = ref(new Set<Chat.ContextProviderName>())
const abortControllers = ref(new Map<Chat.ContextProviderName, AbortController>())
async function loadSubmenuItems(providers: "all" | Chat.ContextProviderName | string[]) {
  const contextProviders = availableContextProviders.value
  if (!contextProviders) {
    return
  }

  await Promise.allSettled(
    contextProviders.map(
      async (description) => {
        const controller = new AbortController()
        try {
          const refreshProvider
                = providers === "all"
                  ? true
                  : providers.includes(description.title)

          if (!refreshProvider) {
            return
          }

          // Submenu loading requests cancel existing requests
          abortControllers.value.get(description.title as Chat.ContextProviderName)?.abort()
          abortControllers.value.set(description.title as Chat.ContextProviderName, controller)
          providersLoading.value.add(description.title as Chat.ContextProviderName)

          const result = await requestWithEventBus<ContextSubmenuItem[]>(submenuBus, "request:context/loadSubmenuItems", "response:context/loadSubmenuItems", {
            title: description.title,
          })

          // IMPORTANT - the controller only prevents invalid loading state
          // But does not cancel using data from the request
          // Could uncomment this to truly cancel the request
          // if (controller.signal.aborted) {
          //   return console.debug(
          //     `${description.title} provider loading aborted`,
          //   );
          // }

          if (result.status === "error") {
            throw new Error(result.error)
          }
          const submenuItems = result.content
          const providerTitle = description.title

          const itemsWithProvider = submenuItems.map(item => ({
            ...item,
            providerTitle,
          }))

          const minisearch = new MiniSearch<ContextSubmenuItemWithProvider>(
            {
              fields: ["title", "description"],
              storeFields: ["id", "title", "description", "providerTitle", "icon"],
            },
          )

          minisearch.addAll(
            submenuItems.map(item => ({ ...item, providerTitle })),
          )

          setMinisearch(providerTitle, minisearch as any)

          setFallbackResults(providerTitle, itemsWithProvider)
        }
        catch (error) {
          console.error(
            `Error loading items for ${description.title}:`,
            error,
          )
          console.error(
            "Error details:",
            JSON.stringify(error, Object.getOwnPropertyNames(error)),
          )
        }
        finally {
          if (!controller.signal.aborted) {
            // providersLoading.delete(description.title)
          }
        }
      },
    ),
  )
}

submenuBus.on(async (event, payload: { submenuItems: ContextSubmenuItem[], provider: "all" | Chat.ContextProviderName }) => {
  if (event === "refreshSubmenuItems") {
    await loadSubmenuItems(payload.provider)
  }
  else if (event === "updateSubmenuItems") {
    const minisearch = new MiniSearch<ContextSubmenuItem>({
      fields: ["title", "description"],
      storeFields: ["id", "title", "description"],
    })

    minisearch.addAll(payload.submenuItems)

    setMinisearch(payload.provider, minisearch)

    if (payload.provider === "protocol") {
      const protocolItems: ContextSubmenuItem[] = []

      setFallbackResults(payload.provider, [
        ...protocolItems,
        ...payload.submenuItems.slice(0, MAX_LENGTH - protocolItems.length),
      ])
    }
    else if (payload.provider === "record") {
      const recordItems: ContextSubmenuItem[] = []
      setFallbackResults(payload.provider, [
        ...recordItems,
        ...payload.submenuItems.slice(0, MAX_LENGTH - recordItems.length),
      ])
    }
    else {
      setFallbackResults(payload.provider, payload.submenuItems.slice(0, MAX_LENGTH))
    }
    setLoaded(true)
  }
  else if (event === "request:context/loadSubmenuItems") {
    const { title } = payload as any

    const provider = (session.value?.config || defaultConfig).contextProviders?.find(
      item => item.description?.title === title,
    )
    if (!provider) {
      return []
    }

    try {
      const items = await provider.loadSubmenuItems({
        eventBus: submenuBus,
        eventName: "response:context/loadSubmenuItems",
        config: {},
      })
      return items
    }
    catch (e) {
      return []
    }
  }
  else if (event === "request:context/getContextItems") {
    const { name, query, fullInput } = payload as any

    const provider = (session.value?.config || defaultConfig).contextProviders?.find(
      item => item.description?.title === name,
    )
    if (!provider) {
      return []
    }

    try {
      const id: ContextItemId = {
        providerTitle: provider.description?.title || "",
        itemId: nanoid(),
      }

      const items = await provider.getContextItems(query, {
        fullInput,
        config: {},
        eventBus: submenuBus,
        eventName: "response:context/getContextItems",
      } as any)

      return items.map(item => ({
        ...item,
        id,
      }))
    }
    catch (e) {
      return []
    }
  }

  //   useEffect(() => {
  //   if (!submenuContextProviders.length || initialLoad.current) {
  //     return;
  //   }
  //   void loadSubmenuItems("all");
  //   initialLoad.current = true;
  // }, [loadSubmenuItems, submenuContextProviders, initialLoad]);
  /*

    on("context/loadSubmenuItems", async (msg) => {
      const config = await this.config();
      const items = await config.contextProviders
        ?.find((provider) => provider.description.title === msg.data.title)
        ?.loadSubmenuItems({
          config,
          ide: this.ide,
          fetch: (url, init) =>
            fetchwithRequestOptions(url, init, config.requestOptions),
        });
      return items || [];
    });

    on("context/getContextItems", async (msg) => {
      const { name, query, fullInput, selectedCode } = msg.data;
      const config = await this.config();
      const llm = await this.getSelectedModel();
      const provider = config.contextProviders?.find(
        (provider) => provider.description.title === name,
      );
      if (!provider) {
        return [];
      }

      try {
        const id: ContextItemId = {
          providerTitle: provider.description.title,
          itemId: uuidv4(),
        };

        const items = await provider.getContextItems(query, {
          config,
          llm,
          embeddingsProvider: config.embeddingsProvider,
          fullInput,
          ide,
          selectedCode,
          reranker: config.reranker,
          fetch: (url, init) =>
            fetchwithRequestOptions(url, init, config.requestOptions),
        });

        Telemetry.capture(
          "useContextProvider",
          {
            name: provider.description.title,
          },
          true,
        );

        return items.map((item) => ({
          ...item,
          id,
        }));
      } catch (e) {
        this.ide.errorPopup(`Error getting context items from ${name}: ${e}`);
        return [];
      }
    });
  */
})

const initialLoad = ref(false)

onMounted(() => {
  if (!availableContextProviders.value.length || initialLoad.value) {
    return
  }
  void loadSubmenuItems("all")
  initialLoad.value = true
})

const activeRef = ref(false)
const editor = useEditor({
  content: prompt.value,
  extensions: [
    Document,
    Text,
    TiptapHistory,
    Paragraph.extend({
      addKeyboardShortcuts() {
        return {
          "Enter": () => {
            if (inDropdownRef.value) {
              return false
            }

            handleSubmit()
            return true
          },

          "Cmd-Enter": () => {
            handleSubmit()
            return true
          },
          "Alt-Enter": () => {
            handleSubmit()
            return true
          },
          "Cmd-Backspace": () => {
            // If you press cmd+backspace wanting to cancel,
            // but are inside of a text box, it shouldn't
            // delete the text
            if (activeRef.value) {
              return true
            }

            return false
          },
          "Shift-Enter": () =>
            this.editor.commands.first(({ commands }) => [
              () => commands.newlineInCode(),
              () => commands.createParagraphNear(),
              () => commands.liftEmptyBlock(),
              () => commands.splitBlock(),
            ]),

          "ArrowUp": () => {
            if (this.editor.state.selection.anchor > 1) {
              return false
            }

            // TODO: Input history

            // const previousInput = prevRef.current(
            //   this.editor.state.toJSON().doc,
            // );
            // if (previousInput) {
            //   this.editor.commands.setContent(previousInput);
            //   setTimeout(() => {
            //     this.editor.commands.blur();
            //     this.editor.commands.focus("start");
            //   }, 0);
            //   return true;
            // }

            return false
          },
          "ArrowDown": () => {
            if (
              this.editor.state.selection.anchor
              < this.editor.state.doc.content.size - 1
            ) {
              return false
            }

            // TODO: Input history

            // const nextInput = nextRef.current();
            // if (nextInput) {
            //   this.editor.commands.setContent(nextInput);
            //   setTimeout(() => {
            //     this.editor.commands.blur();
            //     this.editor.commands.focus("end");
            //   }, 0);
            //   return true;
            // }

            return false
          },
        }
      },
    }).configure({
      HTMLAttributes: {
        class: "my-1",
      },
    }),
    HardBreak,
    Code,
    // CodeBlock,
    // Blockquote,
    // Blockquote,
    Placeholder.configure({
      placeholder: () => resolvedPlaceholder.value,
      emptyEditorClass: "chat-input__placeholder",
    }),
    SlashCommand.configure({
      HTMLAttributes: {
        class: "chat-input__slash-command",
      },
      suggestion: getSlashCommandDropdownOptions(
        availableSlashCommands,
        onClose,
        onOpen,
      ),
      renderText: (props) => {
        return props.node.attrs.label
      },
    }),
    Mention.configure({
      HTMLAttributes: {
        class: "mention chat-input__mention",
      },
      suggestion: getContextProviderDropdownOptions({
        availableContextProviders,
        getSubmenuContextItems,
        enterSubmenu,
        onClose,
        onOpen,
        onUpdate,
        inSubmenu: inSubmenuRef,
      },
      ),
      renderHTML: (props) => {
        return `@${props.node.attrs.label || props.node.attrs.id}`
      },
    }),
  ],
  editorProps: {
    attributes: {
      class: "tiptap-input-editor",
    },
  },
  onUpdate: ({ editor }) => {
    prompt.value = ""
  },
  onFocus: () => {
    focusedRef.value = true
  },
  onBlur: () => {
    focusedRef.value = false
  },
})

watch(prompt, (value) => {
  editor.value?.commands.setContent(value)
  editor.value?.commands.focus("end")
})

// Add selection bus handler after editor initialization
bubbleMenuEventBus.on((event, payload) => {
  if (event !== "sendToChat" && event !== "addToChat") {
    return
  }

  if (typeof payload === "string") {
    if (event === "sendToChat") {
      const promptWrappedText = {
        type: "doc",
        content: [
          {
            type: "paragraph",
            content: [{ type: "text", text: "```" }],
          },
          {
            type: "paragraph",
            content: [{ type: "text", text: payload }],
          },
          {
            type: "paragraph",
            content: [{ type: "text", text: "```" }],
          },
          {
            type: "paragraph",
            content: [{ type: "text", text: "Could you explain this text in detail and highlight any important considerations?" }],
          },
        ],
      }

      editor.value?.commands.setContent(promptWrappedText)
      handleSubmit()
    }
    else if (event === "addToChat") {
      // If there's existing content, add a newline
      if (editor.value?.getText().trim()) {
        editor.value?.commands.setContent(`${editor.value?.getText()}\n${payload}`)
      }
      else {
        editor.value?.commands.setContent(payload)
      }
      editor.value?.commands.focus("end")
    }
  }
  else if (typeof payload === "object") {
    const { prop, value, scope, mentionAttrs, type } = payload as AddToChatPayload

    if (event === "sendToChat") {
      const promptWrappedText = `{{${scope}|${prop}, value=${value || ""}, type=${type}}} Could you explain this field in detail and highlight any important considerations?`

      editor.value?.commands.setContent(promptWrappedText)
      handleSubmit()
    }
    else if (event === "addToChat") {
      const range = editor.value?.state.selection
      if (!range)
        return

      editor.value?.chain()
        .focus()
        .insertContentAt(range, [
          {
            type: "mention",
            attrs: mentionAttrs,
          },
          {
            type: "text",
            text: " ",
          },
        ])
        .run()

      editor.value?.commands.focus("end")
    }
  }
},

)

const buttonDisabled = computed(() => {
  if (loading.value) {
    return false
  }

  if (inputMethod.value === "audio") {
    return isRecording.value
  }

  if (attachments.value?.some(item => item.isUploading)) {
    return true
  }

  return editor.value?.getText().trim() === ""
})

// function handleKeydown(e: KeyboardEvent) {
//   if (e.key === "Enter" && !e.shiftKey) {
//     e.preventDefault()
//     if (!props.loading) {
//       handleSubmit()
//     }
//   }
// }

async function handleSubmit() {
  const editorState = editor.value?.state.toJSON().doc
  const [contextItems, selectedCode, content] = await resolveEditorContent(editorState, submenuBus)

  if (!content || (typeof content === "string" && content.trim() === "")) {
    return
  }
  if (Array.isArray(content) && content.length === 0) {
    return
  }

  if (inputMethod.value === "audio") {
    await handleAudioSave()
    return
  }

  console.log("handleSubmit", content)
  editor.value?.commands.clearContent()
  const type = props.source === "protocol" ? selectedRole.value : ChatType.NORMAL
  const submittedText = typeof content === "string"
    ? content
    : content.map(part => part.text).join("\n")

  if (props.submitHandler) {
    await props.submitHandler(submittedText)
  }
  else {
    await storeHandleSubmit(submittedText, type, selectedModel.value)
  }
}

async function handleClick() {
  if (loading.value) {
    await handleStop()
    emit("stop")
  }
  else {
    await handleSubmit()
  }
}

const message = useClosableMessage()

async function handleAudioSave() {
  await handleRecordingStopped()
}

async function handleRecordingStopped() {
  isProcessingAudio.value = true
  try {
    const blob = audioRecorder.value.audioBlob
    if (!blob) {
      message.error("No audio recording available")
      return
    }

    const formData = new FormData()
    formData.append("audio", blob)

    const response = await fetch(sttEndpoint.value, {
      method: "POST",
      headers: {
        "Auth-Token": token.value || "",
      },
      body: formData,
    })

    if (!response.ok) {
      throw new Error(`STT Request failed: ${response.status}`)
    }

    const data = await response.json()
    const text = data.text || data.content || data.message || data.transcript || (typeof data === "string" ? data : "")

    if (text) {
      const currentText = editor.value?.getText() || ""
      const newText = currentText ? `${currentText} ${text}` : text
      editor.value?.commands.setContent(newText)
    }
    else {
      console.warn("STT Response did not contain expected text field:", data)
      message.warning("Could not transcribe audio")
    }
  }
  catch (error) {
    message.error("Failed to process audio recording")
    console.error("Audio processing error:", error)
  }
  finally {
    isProcessingAudio.value = false
    inputMethod.value = "text"
    resetAudioRecorder()
  }
}

// function handleDeepResearch() {
//   if (!deepResearch.value) {
//     selectedModel.value = ChatModel.BASIC
//   }
//   deepResearch.value = !deepResearch.value
// }
// const themeVars = useThemeVars() as ComputedRef<ThemeCommonVars & CustomThemeCommonVars & {
//   maxWidth: string
//   maxHeight: string
//   minWidth: string
//   minHeight: string
//   bgColor: string
// }>

const cursor = computed(() => {
  if (isRecording.value || inputMethod.value === "audio") {
    return "default"
  }
  return "auto"
})
const inputMethodDisplay = computed(() => {
  if (inputMethod.value === "audio") {
    return "none"
  }
  return "block"
})

function handleScroll(e: WheelEvent) {
  const scrollbarInst = unref(scrollbarRef)
  if (!scrollbarInst) {
    return
  }

  // Normalize delta values - different devices/browsers may have different scales
  const deltaY = e.deltaY
  const scrollAmount = deltaY * 0.5 // Adjust multiplier for scroll sensitivity

  // Use the scrollbar's scrollBy method to manually scroll
  try {
    scrollbarInst.scrollBy(0, scrollAmount)
  }
  catch (error) {
    console.error("Error scrolling scrollbar:", error)
  }

  // Prevent default behavior to avoid any conflicts
  e.preventDefault()
  e.stopPropagation()
}
</script>

<style lang="sass" scoped>
.tiptap-container
  &:hover
    .input__state-border
      border-color: rgb(var(--primary-color))
  &--focus
    .input__state-border
      border-color: rgb(var(--primary-color))
      box-shadow: 0 0 0 2px rgba(26, 121, 255, 0.2)
  .tiptap-input-editor
    padding: 6px 0

.input__border, .input__state-border
  box-sizing: border-box
  position: absolute
  left: 0
  right: 0
  top: 0
  bottom: 0
  pointer-events: none
  border-radius: inherit
  border: 1px solid rgb(var(--border-color))
  transition: box-shadow .3s cubic-bezier(.4, 0, .2, 1), border-color .3s cubic-bezier(.4, 0, .2, 1)

.input__state-border
  border-color: #0000
  z-index: 1

.tiptap-dropzone
  position: relative
  width: 100%

  &__overlay
    position: absolute
    top: 0
    left: 0
    right: 0
    bottom: 0
    display: flex
    flex-direction: column
    align-items: center
    justify-content: center
    pointer-events: none
    border-radius: inherit
    z-index: 10
    color: white

    &::before
      content: ""
      position: absolute
      top: 0
      left: 0
      right: 0
      bottom: 0
      background: rgba(0, 0, 0, 0.4)
      backdrop-filter: blur(4px)
      -webkit-backdrop-filter: blur(4px)
      border-radius: inherit

    // Position icon and text above the overlay
    & > *
      position: relative
      z-index: 11

:deep(.tiptap-input-editor)
  padding: 8px 12px
  outline: none
  overflow-y: auto
  transition: filter 0.2s ease

  p
    margin: 0
    line-height: 1.6

  &.ProseMirror-focused
    outline: none

  blockquote
    border-left: 3px solid rgb(var(--border-color))
    margin: 8px 0
    padding-left: 12px

  pre
    background: rgb(var(--bg-color))
    border-radius: var(--border-radius)
    padding: 8px

  ul, ol
    padding-left: 24px
    margin: 8px 0

    li
      margin: 4px 0

  code
    background: rgb(var(--bg-color))
    border-radius: 4px
    padding: 2px 4px

  .chat-input__placeholder::after
    color: rgba(53, 38, 28, 0.3)
    content: attr(data-placeholder)
    float: left
    pointer-events: none
    margin-top: -1.65em

.recording-interface
  border-radius: 8px
  transition: all 0.3s ease

.recording-icon
  animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite

@keyframes pulse
  0%, 100%
    opacity: 1
  50%
    opacity: 0.3

.file-preview
  transition: all 0.3s ease
  &:hover
    background-color: rgba(0, 0, 0, 0.05)

:deep(.n-input-wrapper)
  flex-wrap: wrap
  height: fit-content
  cursor: v-bind('cursor')

:deep(.n-input__prefix)
  width: 100%
  margin-right: 0

:deep(.n-input__textarea)
  display: v-bind('inputMethodDisplay')

:deep(.chat-input__mention)
  @apply bg-primary-color py-1 px-2 text-white rounded-md

@supports not (backdrop-filter: blur(4px))
  .tiptap-dropzone__overlay::before
    background: rgba(0, 0, 0, 0.7)
</style>

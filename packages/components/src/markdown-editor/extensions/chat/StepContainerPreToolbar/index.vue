<template>
  <div class="min-w-0 flex flex-col b-1 rounded-lg bg-[#fafafa]">
    <div
      class="sticky top-0 flex items-center gap-1.5 overflow-hidden rounded-lg bg-[#f5f5f5] py-1 pl-3.5 pr-1.5"
      :class="isExpanded ? 'rounded-t-default border-command-border border-b' : 'rounded-default'"
    >
      <!-- <ChevronDownIcon
          data-testid="toggle-codeblock"
          class="text-lightgray h-3.5 w-3.5 flex-shrink-0 cursor-pointer hover:brightness-125"
          :class="isExpanded ? 'rotate-0' : '-rotate-90' "
          @click="setIsExpanded"
        /> -->
      <file-info v-if="displayFilepath" :filepath="displayFilepath" :range="range" @click="onClickFilename" />
      <span v-else class="text-lightgray select-none capitalize"> {{ language }} </span>

      <tooltip-button size="small" quaternary :icon="ChevronDownIcon" :icon-props="{ class: isExpanded ? 'rotate-90' : '' }" class="mr-auto" :tooltip="isExpanded ? 'Collapse' : 'Expand'" @click="toggleExpanded" />
      <template v-if="!isGeneratingCodeBlock">
        <!-- <InsertButton on-insert="{@clickInsertAtCursor}" /> -->

        <copy-to-clip :text="codeBlockContent" :button-props="actionButtonProps" :icon-props="{ size: 14 }" :show-text="false">
          {{ $t('chat.copy') }}
        </copy-to-clip>
        <n-button v-bind="actionButtonProps" @click="handleDownloadSnippet">
          <template #icon>
            <n-icon :size="14">
              <icon-carbon-download />
            </n-icon>
          </template>
          {{ $t('chat.common.download') }}
        </n-button>

        <!-- {renderActionButtons()} -->
      </template>
    </div>
    <!-- <collapsible-container v-if="isExpanded" :collapsible="props.collapsible" class="px-1.5 py-1">
      <slot />
    </collapsible-container> -->
    <n-collapse-transition v-show="isExpanded">
      <div class="overflow-auto px-3.5 py-1">
        <slot />
      </div>
    </n-collapse-transition>
  </div>
</template>

<script lang="tsx" setup>
import type { ButtonProps } from "naive-ui"
import CopyToClip from "@airalogy/components/copy-to-clip.vue"
import TooltipButton from "@airalogy/components/tooltip-button.vue"
import { useBoolean } from "@airalogy/composables"
import { $t } from "@airalogy/shared/locales"
import { downloadAs, EXTENSION_MAP } from "@airalogy/shared/utils"
import ChevronDownIcon from "~icons/ion/chevron-down"
import { nanoid } from "nanoid"
import FileInfo from "./FileInfo.vue"

// import { inferResolvedUriFromRelativePath } from "core/util/ideUtils"
// import { useContext, useEffect, useMemo, useState } from "react"
// import { IdeMessengerContext } from "../../../context/IdeMessenger"
// import { useIdeMessengerRequest } from "../../../hooks/useIdeMessengerRequest"
// import { useWebviewListener } from "../../../hooks/useWebviewListener"
// import { useAppSelector } from "../../../redux/hooks"
// import { selectApplyStateByStreamId, selectApplyStateByToolCallId, } from "../../../redux/slices/sessionSlice"
// import { getFontSize } from "../../../util"
// import Spinner from "../../gui/Spinner"
// import { isTerminalCodeBlock } from "../utils"
// import { ApplyActions } from "./ApplyActions"
// import { CollapsibleContainer } from "./CollapsibleContainer"
// import { CopyButton } from "./CopyButton"
// import { CreateFileButton } from "./CreateFileButton"
// import { FileInfo } from "./FileInfo"
// import { InsertButton } from "./InsertButton"
// import { RunInTerminalButton } from "./RunInTerminalButton"

export interface StepContainerPreToolbarProps {
  codeBlockContent: string
  language: string | null
  relativeFilepath?: string
  itemIndex?: number
  codeBlockIndex: number // To track which codeblock we are applying
  isLastCodeblock: boolean
  codeBlockStreamId: string
  forceToolCallId?: string // If this is defined, we will use this streamId instead of the one from the codeBlock
  range?: string
  children: any
  expanded?: boolean
  disableManualApply?: boolean
  collapsible?: boolean
}

//  function StepContainerPreToolbar({
//   codeBlockContent,
//   language,
//   relativeFilepath,
//   itemIndex,
//   codeBlockIndex,
//   isLastCodeblock,
//   codeBlockStreamId,
//   forceToolCallId,
//   range,
//   children,
//   expanded,
//   disableManualApply,
//   collapsible,
// }: StepContainerPreToolbarProps)
const props = defineProps<StepContainerPreToolbarProps>()
// const ideMessenger = useContext(IdeMessengerContext)
// const history = useAppSelector(state => state.session.history)
// const [isExpanded, setIsExpanded] = useState(expanded ?? true)
const { bool: isExpanded, toggle: toggleExpanded } = useBoolean(true)
const actionButtonProps: ButtonProps = { size: "small", type: "default", iconPlacement: "left", quaternary: true, text: false }

const relativeFilepathUri = ref<string | null>(null)

// const fileExistsInput = useMemo(
//   () => (relativeFilepathUri ? { filepath: relativeFilepathUri } : null),
//   [relativeFilepathUri],
// )

// const {
//   result: fileExists,
//   refresh: refreshFileExists,
//   isLoading: isLoadingFileExists,
// } = useIdeMessengerRequest("fileExists", fileExistsInput)

// const nextCodeBlockIndex = useAppSelector(
//   state => state.session.codeBlockApplyStates.curIndex,
// )

// const applyState = useAppSelector(state =>
//   selectApplyStateByStreamId(state, codeBlockStreamId),
// )
// const toolCallApplyState = useAppSelector(state =>
//   selectApplyStateByToolCallId(state, forceToolCallId),
// )

/**
 * In the case where `relativeFilepath` is defined, this will just be `relativeFilepathUri`.
 * However, if no `relativeFilepath` is defined, then this will
 * be the URI of the currently open file at the time the user clicks "Apply".
 */
const appliedFileUri = ref<string | undefined>()

const relativeFilepath = ref("")
const hasFileExtension = computed(() => relativeFilepath.value && /\.[0-9a-z]+$/i.test(relativeFilepath.value))

// const isStreaming = useAppSelector(store => store.session.isStreaming)
const isStreaming = ref(false)

const isLastItem = computed(() => props.itemIndex === history.length - 1)

const isGeneratingCodeBlock = computed(() => isLastItem.value && props.isLastCodeblock && isStreaming.value)

// If we are creating a file, we already render that in the button
// so we don't want to dispaly it twice here
const displayFilepath = computed(() => relativeFilepath.value ?? appliedFileUri.value)

// TODO: This logic should be moved to a thunk
// Handle apply keyboard shortcut
// useWebviewListener(
//   "applyCodeFromChat",
//   async () => @clickApply(),
//   [isNextCodeBlock, codeBlockContent],
//   !isNextCodeBlock,
// )
async function inferResolvedUriFromRelativePath(
  _relativePath: string,
  dirCandidates?: string[],
): Promise<string> {
  return _relativePath
}

watch(relativeFilepath, () => {
  const getRelativeFilepathUri = async () => {
    if (relativeFilepath.value) {
      const resolvedUri = await inferResolvedUriFromRelativePath(
        relativeFilepath.value,
      )
      // setRelativeFilepathUri(resolvedUri)
      relativeFilepath.value = resolvedUri
    }
  }
  void getRelativeFilepathUri()
})

async function getFileUriToApplyTo() {
  // If we've already resolved a file URI (from clicking apply), use that
  if (appliedFileUri.value) {
    return appliedFileUri
  }

  // If we have the `relativeFilepathUri`, use that
  if (relativeFilepathUri.value) {
    return relativeFilepathUri.value
  }

  // If no filepath was provided, get the current file
  // const currentFile = await ideMessenger.ide.getCurrentFile()
  // if (currentFile) {
  //   return currentFile.path
  // }

  return undefined
}

async function onClickFilename() {
  // if (appliedFileUri.value) {
  //   ideMessenger.post("showFile", {
  //     filepath: appliedFileUri,
  //   })
  // }

  // if (relativeFilepath.value) {
  //   const filepath = await inferResolvedUriFromRelativePath(
  //     relativeFilepath,
  //     ideMessenger.ide,
  //   )

  //   ideMessenger.post("showFile", {
  //     filepath,
  //   })
  // }
}

// const renderActionButtons = () => {
//   const isPendingToolCall = toolCallApplyState?.status === "not-started"

//   if (isGeneratingCodeBlock || isPendingToolCall) {
//     const numLines = codeBlockContent.split("\n").length
//     const plural = numLines === 1 ? "" : "s"
//     if (isGeneratingCodeBlock) {
//       return (
//         <span class="text-lightgray inline-flex items-center gap-2 text-right">
//           <div>
//             <Spinner />
//           </div>
//         </span>
//       )
//     }
//     else {
//       return (
//         <span class="text-lightgray inline-flex items-center gap-2 text-right">
//           {`${numLines} line${plural} pending`}
//         </span>
//       )
//     }
//   }

//   if (isTerminalCodeBlock(language, codeBlockContent)) {
//     return <RunInTerminalButton command={codeBlockContent} />
//   }

//   if (isLoadingFileExists) {
//     return null
//   }

//   if (fileExists || !relativeFilepath) {
//     return (
//       <ApplyActions
//         disableManualApply={disableManualApply}
//         applyState={toolCallApplyState ?? applyState}
//         @clickApply={@clickApply}
//         @clickAccept={() => handleDiffAction("accept")}
//         @clickReject={() => handleDiffAction("reject")}
//       />
//     )
//   }

//   return <CreateFileButton @click={@clickApply} />
// }

// // We wait until there is an extension in the filepath to avoid rendering
// // an incomplete filepath
// if (relativeFilepath && !hasFileExtension) {
//   return children
// }

function handleDownloadSnippet() {
  const ext = EXTENSION_MAP[props.language as any] || "txt"
  downloadAs(props.codeBlockContent, `airalogy_chat_${props.language}_${nanoid()}.${ext}`)
}
</script>

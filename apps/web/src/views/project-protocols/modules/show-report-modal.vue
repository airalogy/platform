<template>
  <n-drawer
    :show="isShown"
    class="mx-4vw min-w-180"
    :mask-closable="false"
    :theme-overrides="{ borderRadius: '1.5rem' }"
    header-class="py-7"
    height="calc(100vh - 4.375rem)"
    placement="bottom"
    @update-show="handleUpdateShow"
    @after-leave="handleTransitionEnd"
  >
    <n-drawer-content closable>
      <template #header>
        <div class="w-full flex flex-1 flex-row items-center">
          <h3 class="text-5 font-500">
            {{ props.title }}
          </h3>
          <span />
        </div>
      </template>
      <n-spin
        :show="loading"
        class="h-full w-full"
        :content-class="`h-full w-full${props.record ? '' : ' flex-center flex-col'}`"
      >
        <template v-if="props.record">
          <markdown-preview
            text=""
            :field="props.record.data"
            mode="report"
            @mounted:field="handleMountedField"
          />
          <!-- <report-teleport v-if="isFieldMounted" :data="props.record.data" /> -->
          <!-- <asset-teleport
            v-if="isFieldMounted && props.record?.metadata?.airalogy_protocol_id"
            :uuid="props.record?.metadata?.airalogy_protocol_id"
          /> -->
        </template>
        <template v-else-if="!loading && isFieldMounted">
          Error
        </template>
      </n-spin>
    </n-drawer-content>
  </n-drawer>
</template>

<script setup lang="ts">
import type { ProtocolModels } from "@airalogy/shared/types"
import { useBoolean, useLoading, useShowModal } from "@/composables/"
import { getStaticResearchAssets } from "@/service/api/project-protocols"
import MarkdownPreview from "@airalogy/components/file-preview/markdown-preview.vue"
import { useClosableMessage } from "@airalogy/composables"

defineOptions({ name: "ShowReportModal" })

const props = withDefaults(defineProps<IProps>(), {
  record: null,
  title: "Record report",
})

const emits = defineEmits<IEmits>()

interface IProps {
  record: ProtocolModels.RecordInfo | null
  title?: string
}

const { loading } = useLoading()
const message = useClosableMessage()

interface IEmits {
  (e: "update:show", show: boolean): void
}
const { isShown, hideModal, showModal, setModalStatus } = useShowModal()
const { bool: isFieldMounted, setTrue: setFieldMounted, setFalse: setFieldUnMounted } = useBoolean()

const handleUpdateShow = (show: boolean) => setModalStatus(show)

function handleTransitionEnd() {
  setFieldUnMounted()
  emits("update:show", isShown.value)
}

function handleImages(imageList: HTMLImageElement[]) {
  if (!props.record?.metadata?.airalogy_protocol_id) {
    return
  }

  imageList.forEach(async (image) => {
    const src = image.getAttribute("src")
    if (!src) {
      return
    }

    try {
      const filename = src.split("/").slice(1).join("/")
      if (!filename) {
        return
      }

      const res = await getStaticResearchAssets(props.record!.metadata.airalogy_protocol_id, filename)
      if (res && res.data) {
        image.src = res.data.url
      }
    }
    catch (e) {
      message.error((e as Error).message)
    }
  })
}

watch(
  () => props.record,
  (data) => {
    if (data) {
      showModal()
    }
  },
)

// function handleMedia(sourceList: HTMLSourceElement[]) {
//   if (!props.record || !props.record.metadata?.airalogy_protocol_id) {
//     return
//   }

//   sourceList.forEach(async (source) => {
//     const src = source.getAttribute("src")
//     if (!src) {
//       return
//     }

//     try {
//       const res = await getStaticResearchAssets(props.record!.metadata.airalogy_protocol_id, src)
//       if (res && res.data) {
//         const parent = source.parentElement

//         if (parent) {
//           source.src = res.data.url
//           // eslint-disable-next-line no-self-assign
//           parent.outerHTML = parent.outerHTML
//         }
//       }
//     }
//     catch (e) {
//       message.error((e as Error).message)
//     }
//   })
// }

function handleMountedField() {
  setFieldMounted()

  // const images = Array.from(document.querySelectorAll<HTMLImageElement>(".markdown-body img") || [])

  // if (images.length > 0) {
  //   void handleImages(images)
  // }

  // const sourceList = Array.from(
  //   document.querySelectorAll<HTMLSourceElement>(".markdown-body source") || [],
  // )

  // if (sourceList.length > 0) {
  //   void handleMedia(sourceList)
  // }
}
</script>

<style scoped></style>

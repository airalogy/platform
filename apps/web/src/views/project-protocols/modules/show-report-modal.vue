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
        <template v-if="props.record && props.aimd">
          <readonly-record-preview
            :aimd="props.aimd"
            :record="props.record"
          />
        </template>
        <template v-else-if="!loading">
          Error
        </template>
      </n-spin>
    </n-drawer-content>
  </n-drawer>
</template>

<script setup lang="ts">
import type { ProtocolModels } from "@airalogy/shared/types"
import { useLoading, useShowModal } from "@/composables/"
import ReadonlyRecordPreview from "./readonly-record-preview.vue"

defineOptions({ name: "ShowReportModal" })

const props = withDefaults(defineProps<IProps>(), {
  aimd: "",
  record: null,
  title: "Record report",
})

const emits = defineEmits<IEmits>()

interface IProps {
  aimd?: string
  record: ProtocolModels.RecordInfo | null
  title?: string
}

const { loading } = useLoading()

interface IEmits {
  (e: "update:show", show: boolean): void
}
const { isShown, showModal, setModalStatus } = useShowModal()

const handleUpdateShow = (show: boolean) => setModalStatus(show)

function handleTransitionEnd() {
  emits("update:show", isShown.value)
}

watch(
  () => props.record,
  (data) => {
    if (data) {
      showModal()
    }
  },
)
</script>

<style scoped></style>

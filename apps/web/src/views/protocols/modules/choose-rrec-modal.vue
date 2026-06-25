<template>
  <n-button tertiary type="primary" @click="showModal">
    <span>Select RREC</span>
  </n-button>
  <n-modal
    :show="isShown"
    title="Select record version"
    :show-icon="false"
    preset="dialog"
    class="rrec__modal min-w-600px"
    @close="hideModal"
    @after-leave="restoreModel"
  >
    <n-form v-if="props.rrec" :model="model">
      <n-form-item label="Current rrec id">
        <n-input disabled :value="props.rrec.rrec_airalogy_id" />
      </n-form-item>
      <n-form-item label="Date Range">
        <n-date-picker v-model="model.dateStart" placeholder="Start Date" />
        <span class="mx-4">-</span>
        <n-date-picker v-model="model.dateEnd" placeholder="End Date" />
      </n-form-item>

      <n-form-item label="Select Version">
        <n-select v-model="model.version" :options="versions" placeholder="Select Version" />
      </n-form-item>

      <n-form-item label="Select Recent Versions">
        <n-select
          v-model="model.recentVersions"
          :disabled="Boolean(model.version)"
          :options="recentVersions"
          placeholder="Select Recent Versions"
          multiple
        />
      </n-form-item>
      <n-flex>
        <n-button class="ml-auto" @click="hideModal">
          Select all
        </n-button>
        <n-button type="primary" @click="hideModal">
          Confirm
        </n-button>
      </n-flex>
    </n-form>
    <div v-else>
      No RREC found
    </div>
  </n-modal>
</template>

<script setup lang="ts">
import type { SelectMixedOption } from "naive-ui/es/select/src/interface"
import { useShowModal } from "@/composables"

defineOptions({ name: "ChooseRrecModal", inheritAttrs: false })

const props = defineProps<IProps>()

interface IProps {
  rrec: any
  show?: boolean
}

const { isShown, hideModal, showModal, setModalStatus } = useShowModal()

interface ISelectParams {
  dateStart?: Date | null
  dateEnd?: Date | null
  version?: string | null
  recentVersions?: string[]
}

const initModel: ISelectParams = {
  dateStart: null,
  dateEnd: null,
  version: null,
  recentVersions: [],
}
const model = ref<ISelectParams>({ ...initModel })

const versions = computed<SelectMixedOption[]>(() => {
  if (!props.rrec?.metadata?.rn_ver) {
    return []
  }

  const [main, minor, patch] = (props.rrec.metadata.rn_ver as string).split(".")

  const options = Array.from({ length: Number(patch) + 1 })
    .map((_, i) => ({
      label: `${main}.${minor}.${i}`,
      value: `${main}.${minor}.${i}`,
    }))
    .reverse()

  return options
}) // Populate with available versions
const recentVersions = computed<SelectMixedOption[]>(() => {
  if (!props.rrec?.metadata?.rn_ver) {
    return []
  }

  const [main, minor, patch] = (props.rrec.metadata.rn_ver as string).split(".")
  const options = Array.from({ length: Number(patch) + 1 })
    .map((_, i) => ({
      label: `${main}.${minor}.${i}`,
      value: `${main}.${minor}.${i}`,
    }))
    .reverse()

  return options
}) // Populate with recent versions

function restoreModel() {
  model.value = { ...initModel }
}

watchEffect((onCleanup) => {
  const cancelRequest = () => {}

  onCleanup(cancelRequest)
})

watch(

  () => props.rrec,
  (rrec) => {
    model.value.recentVersions = props.rrec?.metadata?.rn_ver
    model.value.recentVersions = props.rrec?.metadata?.rn_ver
  },
)
watch(
  () => props.show,
  (show) => {
    if (show) {
      showModal()
    }
  },
)
</script>

<style scoped lang="sass"></style>

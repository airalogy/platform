<template>
  <n-modal
    v-model:show="isManualResearchNodeShown"
    title="Choose next protocol"
    preset="card"
    class="max-w-70vw min-w-2xl"
    @after-leave="checkedRowKeys = []"
  >
    <div v-if="manualSelectedNextNode" class="mb-4 flex items-center">
      <div class="mr-3">
        Selected Research Protocol:
      </div>
      <n-tag class="mr-2" type="primary">
        {{ manualSelectedNextNode.uid }}
      </n-tag>
      <div>({{ manualSelectedNextNode.name }})</div>
    </div>
    <div v-else class="mb-4">
      No protocol selected.
    </div>
    <n-data-table
      v-model:checked-row-keys="checkedRowKeys"
      :columns="columns"
      :data="nodeListData"
      :pagination="{ page: currentPage, pageSize: currentPageSize }"
      :row-key="(it : any) => it.id"
      max-height="50vh"
    />

    <template #action>
      <n-flex>
        <ai-button class="mx-2 mr-auto" tooltip="Let AI choose the next protocol" :button-props="{ onClick: handleAISelect }">
          AI
        </ai-button>
        <n-button class="ml-auto" @click="hideManualResearchNode">
          Cancel
        </n-button>
        <n-button type="primary" :disabled="!manualSelectedNextNode" @click="handleAddNextRN">
          Confirm
        </n-button>
      </n-flex>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import type { FlowNode, WorkflowModel, WorkflowRecordItem } from "@/store/modules/workflow"
import type { ProtocolModels } from "@airalogy/shared/types/models"
import type { Node } from "@vue-flow/core"
import type { DataTableColumns } from "naive-ui"
import { usePagination } from "@/composables"
import { NDataTable } from "naive-ui"

interface IProps {
  show: boolean
  workflowNodes: Node[]
  workflowModel: WorkflowModel
  flowNodes: FlowNode[]
}

const props = withDefaults(defineProps<IProps>(), {})

const emit = defineEmits<IEmits>()

interface IEmits {
  (e: "update:show", value: boolean): void
  (e: "action:end-workflow", node: any): void
  (e: "action:add-next-node", node: any): void
  (e: "action:ai-select"): void
}

const isManualResearchNodeShown = useVModel(props, "show", emit, { defaultValue: false })

interface NextNodeInfo extends ProtocolModels.ProjectProtocolInfo {
  record: WorkflowRecordItem
}

const nodeListData = computed<NextNodeInfo[]>(() => {
  if (!props.workflowNodes || !props.workflowModel) {
    return []
  }

  return props.workflowNodes
    .map((it) => {
      const node = it.data?.target
      if (!node) {
        return null
      }

      const history = props.workflowModel.record[node.id]

      return { ...node, history }
    })
    .filter((it): it is NextNodeInfo => Boolean(it))
})

const checkedRowKeys = ref([])
const manualSelectedNextNode = computed(() =>
  nodeListData.value.find(({ id }) => id === checkedRowKeys.value[0]),
)

const total = computed(() => nodeListData.value.length)
const { currentPage, currentPageSize } = usePagination({
  options: { page: 1, pageSize: 6, total },
})

const columns: DataTableColumns<NextNodeInfo> = [
  { type: "selection", multiple: false },
  { title: "Name", resizable: true, key: "name" },
  { title: "ID", resizable: true, key: "uid" },
  {
    title: "History",
    key: "history",
    render: (data) => {
      if (!data) {
        return
      }

      const { record: history } = data

      return JSON.stringify(history, null, 0)
    },
  },
]

function handleEndWorkflow() {
  emit("action:end-workflow", manualSelectedNextNode.value)
}
function hideManualResearchNode() {
  isManualResearchNodeShown.value = false
}

function handleAddNextRN() {
  emit("action:add-next-node", manualSelectedNextNode.value)
}

function handleAISelect() {
  emit("action:ai-select")
}
</script>

<style scoped></style>

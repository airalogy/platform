<template>
  <n-button v-if="requirements.length" secondary @click="openModal">
    <template #icon>
      <n-icon><icon-tabler-calendar-plus /></n-icon>
    </template>
    {{ $t("page.research.reserveResource") }}
  </n-button>

  <n-modal
    style="--aira-dialog-width: 44rem"
    v-model:show="visible"
    preset="card"
    class="aira-dialog research-resource-modal"
    :title="$t('page.research.reserveResource')"
    :mask-closable="false"
    @after-leave="reset"
  >
    <template v-if="!preview">
      <n-alert type="info" class="mb-4">
        {{ $t("page.research.resourceReservationHint") }}
      </n-alert>
      <n-form label-placement="top">
        <n-form-item :label="$t('page.research.resourceRequirement')" required>
          <n-select
            v-model:value="draft.resource_type_id"
            :options="requirementOptions"
            @update:value="loadResources"
          />
        </n-form-item>
        <n-form-item :label="$t('page.research.resource')" required>
          <n-select
            v-model:value="draft.resource_id"
            :options="resourceOptions"
            :loading="resourcesLoading"
            :disabled="!draft.resource_type_id"
            filterable
            @update:value="loadResourceDetail"
          />
        </n-form-item>
        <n-form-item v-if="kindOptions.length > 1" :label="$t('page.research.reservationKind')" required>
          <n-select v-model:value="draft.kind" :options="kindOptions" @update:value="resetKindFields" />
        </n-form-item>

        <template v-if="draft.kind === 'inventory'">
          <n-form-item :label="$t('page.research.inventoryContainer')" required>
            <n-select
              v-model:value="draft.container_id"
              :options="containerOptions"
              :disabled="!resourceDetail"
              @update:value="selectContainer"
            />
          </n-form-item>
          <div class="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
            <n-form-item :label="$t('page.research.quantity')" required>
              <n-input v-model:value="draft.quantity" inputmode="decimal" />
            </n-form-item>
            <n-form-item :label="$t('page.research.unit')" required>
              <n-input v-model:value="draft.unit" />
            </n-form-item>
          </div>
          <n-form-item :label="$t('page.research.reservationExpiry')">
            <n-date-picker v-model:value="expiresAt" type="datetime" clearable class="w-full" />
          </n-form-item>
        </template>

        <template v-else-if="draft.kind === 'equipment'">
          <div class="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
            <n-form-item :label="$t('page.research.bookingStarts')" required>
              <n-date-picker v-model:value="startsAt" type="datetime" class="w-full" />
            </n-form-item>
            <n-form-item :label="$t('page.research.bookingEnds')" required>
              <n-date-picker v-model:value="endsAt" type="datetime" class="w-full" />
            </n-form-item>
          </div>
        </template>

        <n-form-item :label="$t('page.research.reservationPurpose')" required>
          <n-input
            v-model:value="draft.purpose"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 8 }"
          />
        </n-form-item>
      </n-form>
    </template>

    <template v-else>
      <n-alert type="warning">
        {{ $t("page.research.resourcePreviewHint") }}
      </n-alert>
      <section class="research-resource-preview mt-4">
        <div class="aira-type-eyebrow">{{ $t("page.research.resource") }}</div>
        <h3 class="aira-type-card-title mb-0 mt-1">
          {{ preview.resource.name }} · {{ preview.resource.code }}
        </h3>
        <div class="aira-type-meta mt-2">
          {{ $t("page.research.resourceRevision", { revision: preview.resource.revision }) }}
        </div>
      </section>
      <section class="research-resource-preview mt-3">
        <div class="aira-type-eyebrow">{{ $t("page.research.effects") }}</div>
        <ul class="aira-type-body aira-text-secondary mb-0 mt-2 pl-5">
          <li v-for="effect in preview.effects" :key="effect">
            {{ effect }}
          </li>
        </ul>
      </section>
    </template>

    <template #footer>
      <div class="flex flex-wrap justify-end gap-2">
        <n-button @click="preview ? preview = null : visible = false">
          {{ preview ? $t("page.research.backToEdit") : $t("common.cancel") }}
        </n-button>
        <n-button
          v-if="!preview"
          type="primary"
          :disabled="!valid"
          :loading="submitting"
          @click="handlePreview"
        >
          {{ $t("page.research.previewReservation") }}
        </n-button>
        <n-button v-else type="primary" :loading="submitting" @click="handleCreate">
          {{ $t("page.research.confirmReservation") }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import type {
  ResearchResourceActionDraft,
  ResearchResourceActionPreview,
} from "@/service/api/research-resources"
import type { ResearchResourceRequirement } from "@/service/api/research-tasks"
import type { ResourceDetail, ResourceItem } from "@/service/api/resources"
import {
  createResearchResourceAction,
  previewResearchResourceAction,
} from "@/service/api/research-resources"
import { fetchResource, fetchResources } from "@/service/api/resources"
import { $t } from "@airalogy/shared/locales"
import { nanoid } from "nanoid"

interface ContainerData {
  id: string
  code: string
  unit: string
  status: string
  balance?: { available: string, unit: string } | null
}

const props = defineProps<{
  taskId: string
  labId: string
  requirements: ResearchResourceRequirement[]
}>()
const emit = defineEmits<{ created: [] }>()

const visible = ref(false)
const submitting = ref(false)
const resourcesLoading = ref(false)
const resources = ref<ResourceItem[]>([])
const resourceDetail = ref<ResourceDetail | null>(null)
const preview = ref<ResearchResourceActionPreview | null>(null)
const expiresAt = ref<number | null>(null)
const startsAt = ref<number | null>(null)
const endsAt = ref<number | null>(null)
const draft = reactive({
  resource_type_id: "",
  kind: "" as "" | "inventory" | "equipment",
  resource_id: "",
  container_id: "",
  quantity: "",
  unit: "",
  purpose: "",
})

const selectedRequirement = computed(() => props.requirements.find(
  item => item.source_id === draft.resource_type_id,
))
const requirementOptions = computed(() => props.requirements.map(item => ({
  label: `${item.name} · r${item.version}`,
  value: item.source_id,
})))
const resourceOptions = computed(() => resources.value.map(item => ({
  label: `${item.name} · ${item.code}`,
  value: item.id,
})))
const kindOptions = computed(() => {
  const capabilities = selectedRequirement.value?.metadata.capabilities || {}
  return [
    capabilities.inventory
      ? { label: $t("page.research.inventoryReservation"), value: "inventory" }
      : null,
    capabilities.booking
      ? { label: $t("page.research.equipmentBooking"), value: "equipment" }
      : null,
  ].filter(Boolean) as Array<{ label: string, value: "inventory" | "equipment" }>
})
const containers = computed<ContainerData[]>(() => (resourceDetail.value?.containers || []) as unknown as ContainerData[])
const containerOptions = computed(() => containers.value
  .filter(item => item.status === "active" && item.balance)
  .map(item => ({
    label: `${item.code} · ${item.balance?.available || "0"} ${item.balance?.unit || item.unit}`,
    value: item.id,
  })))
const valid = computed(() => Boolean(
  draft.resource_type_id
  && draft.resource_id
  && draft.kind
  && draft.purpose.trim()
  && (
    draft.kind === "inventory"
      ? draft.container_id && Number(draft.quantity) > 0 && draft.unit.trim()
      : startsAt.value && endsAt.value && endsAt.value > startsAt.value
  ),
))

function resetKindFields() {
  draft.container_id = ""
  draft.quantity = ""
  draft.unit = ""
  expiresAt.value = null
  startsAt.value = null
  endsAt.value = null
}

function selectContainer(containerId: string) {
  const container = containers.value.find(item => item.id === containerId)
  if (container)
    draft.unit = container.balance?.unit || container.unit
}

async function loadResources(resourceTypeId: string) {
  preview.value = null
  resources.value = []
  resourceDetail.value = null
  draft.resource_id = ""
  resetKindFields()
  const options = kindOptions.value
  draft.kind = options.length === 1 ? options[0].value : ""
  if (!resourceTypeId)
    return
  resourcesLoading.value = true
  try {
    const result = await fetchResources(props.labId, {
      resource_type_id: resourceTypeId,
      status: "active",
      page: 1,
      page_size: 200,
    })
    resources.value = result.items
    if (resources.value.length === 1) {
      draft.resource_id = resources.value[0].id
      await loadResourceDetail(draft.resource_id)
    }
  }
  finally {
    resourcesLoading.value = false
  }
}

async function loadResourceDetail(resourceId: string) {
  preview.value = null
  resourceDetail.value = null
  resetKindFields()
  const options = kindOptions.value
  draft.kind = options.length === 1 ? options[0].value : ""
  if (!resourceId)
    return
  resourceDetail.value = await fetchResource(props.labId, resourceId)
  if (draft.kind === "inventory" && containerOptions.value.length === 1) {
    draft.container_id = containerOptions.value[0].value
    selectContainer(draft.container_id)
  }
}

function payload(): ResearchResourceActionDraft {
  const common = {
    kind: draft.kind as "inventory" | "equipment",
    resource_id: draft.resource_id,
    purpose: draft.purpose.trim(),
    idempotency_key: `resource-${nanoid()}`,
  }
  if (draft.kind === "inventory") {
    return {
      ...common,
      container_id: draft.container_id,
      quantity: draft.quantity,
      unit: draft.unit.trim(),
      expires_at: expiresAt.value ? new Date(expiresAt.value).toISOString() : undefined,
    }
  }
  return {
    ...common,
    starts_at: new Date(startsAt.value as number).toISOString(),
    ends_at: new Date(endsAt.value as number).toISOString(),
  }
}

let previewPayload: ResearchResourceActionDraft | null = null

async function handlePreview() {
  if (!valid.value)
    return
  submitting.value = true
  try {
    previewPayload = payload()
    preview.value = await previewResearchResourceAction(props.taskId, previewPayload)
  }
  finally {
    submitting.value = false
  }
}

async function handleCreate() {
  if (!preview.value || !previewPayload)
    return
  submitting.value = true
  try {
    await createResearchResourceAction(props.taskId, {
      ...previewPayload,
      preview_digest: preview.value.preview_digest,
    })
    window.$message?.success($t("page.research.resourceReserved"))
    visible.value = false
    emit("created")
  }
  finally {
    submitting.value = false
  }
}

async function openModal() {
  visible.value = true
  if (props.requirements.length === 1 && !draft.resource_type_id) {
    draft.resource_type_id = props.requirements[0].source_id
    await loadResources(draft.resource_type_id)
  }
}

function reset() {
  preview.value = null
  previewPayload = null
  resources.value = []
  resourceDetail.value = null
  draft.resource_type_id = ""
  draft.resource_id = ""
  draft.kind = ""
  draft.purpose = ""
  resetKindFields()
}
</script>

<style scoped>
.research-resource-preview {
  border: 1px solid rgb(229 231 235);
  border-radius: 0.75rem;
  background: rgb(249 250 251);
  padding: 1rem;
}
</style>

<template>
  <n-button v-if="services.length" secondary @click="open">
    <template #icon>
      <n-icon><icon-tabler-building-factory-2 /></n-icon>
    </template>
    {{ $t("page.research.requestExternalService") }}
  </n-button>

  <n-modal
    style="--aira-dialog-width: 46rem"
    v-model:show="visible"
    preset="card"
    class="aira-dialog research-service-modal"
    :title="$t('page.research.requestExternalService')"
    :mask-closable="false"
    @after-leave="reset"
  >
    <template v-if="!preview">
      <n-alert type="info" class="mb-4">
        {{ $t("page.research.serviceRequestHint") }}
      </n-alert>
      <n-form label-placement="top">
        <n-form-item :label="$t('page.research.externalService')" required>
          <n-select v-model:value="draft.service_offering_id" :options="serviceOptions" filterable />
          <template #feedback>
            {{ selectedService?.description }}
          </template>
        </n-form-item>
        <n-form-item
          :label="$t('page.research.serviceRequestPayload')"
          required
          :validation-status="requestValid ? undefined : 'error'"
          :feedback="requestValid ? $t('page.research.serviceSchemaHint') : $t('page.research.invalidJsonObject')"
        >
          <n-input
            v-model:value="requestText"
            type="textarea"
            :autosize="{ minRows: 5, maxRows: 14 }"
            class="font-mono"
          />
        </n-form-item>
        <n-collapse v-if="selectedService">
          <n-collapse-item :title="$t('page.research.pinnedContract')" name="contract">
            <pre>{{ JSON.stringify(selectedService.input_schema, null, 2) }}</pre>
          </n-collapse-item>
        </n-collapse>
        <n-form-item :label="$t('page.research.actionTitle')">
          <n-input v-model:value="draft.title" />
        </n-form-item>
        <n-form-item :label="$t('page.research.actionDescription')">
          <n-input v-model:value="draft.description" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" />
        </n-form-item>
      </n-form>
    </template>
    <template v-else>
      <n-alert type="warning">
        {{ $t("page.research.serviceRequestPreviewHint") }}
      </n-alert>
      <section class="service-preview mt-4">
        <div class="aira-type-eyebrow">{{ $t("page.research.externalService") }}</div>
        <h3 class="aira-type-card-title mb-0 mt-1">
          {{ preview.service.metadata.provider.name }} · {{ preview.service.name }}
        </h3>
        <div class="mt-2 flex flex-wrap gap-2">
          <n-tag size="small" type="warning">{{ preview.service.risk }}</n-tag>
          <n-tag size="small">v{{ preview.service.version }}</n-tag>
          <n-tag size="small">
            {{ preview.service.metadata.quote_required ? $t("page.research.quoteRequired") : $t("page.research.catalogPrice") }}
          </n-tag>
        </div>
        <pre class="mt-3">{{ JSON.stringify(preview.command.request_payload, null, 2) }}</pre>
      </section>
      <section class="service-preview mt-3">
        <div class="aira-type-eyebrow">{{ $t("page.research.effects") }}</div>
        <ul class="aira-type-body aira-text-secondary mb-0 mt-2 pl-5">
          <li v-for="effect in preview.effects" :key="effect">{{ effect }}</li>
        </ul>
      </section>
    </template>
    <template #footer>
      <div class="flex justify-end gap-2">
        <n-button @click="preview ? preview = null : visible = false">
          {{ preview ? $t("page.research.backToEdit") : $t("common.cancel") }}
        </n-button>
        <n-button v-if="!preview" type="primary" :disabled="!valid" :loading="submitting" @click="handlePreview">
          {{ $t("page.research.previewAction") }}
        </n-button>
        <n-button v-else type="primary" :loading="submitting" @click="handleCreate">
          {{ $t("page.research.confirmServiceRequest") }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import type { ServiceActionDraft, ServiceActionPreview } from "@/service/api/research-service-jobs"
import type { ResearchServiceRequirement } from "@/service/api/research-tasks"
import { createServiceAction, previewServiceAction } from "@/service/api/research-service-jobs"
import { $t } from "@airalogy/shared/locales"
import { nanoid } from "nanoid"

const props = defineProps<{ taskId: string, services: ResearchServiceRequirement[] }>()
const emit = defineEmits<{ created: [] }>()
const visible = ref(false)
const submitting = ref(false)
const requestText = ref("{}")
const preview = ref<ServiceActionPreview | null>(null)
const previewPayload = ref<ServiceActionDraft | null>(null)
const draft = reactive({ service_offering_id: "", title: "", description: "" })

const selectedService = computed(() => props.services.find(item => item.source_id === draft.service_offering_id))
const serviceOptions = computed(() => props.services.filter(item => item.available).map(item => ({
  label: `${item.metadata.provider.name} · ${item.name} · v${item.version}`,
  value: item.source_id,
})))
const parsedRequest = computed(() => {
  try {
    const value = JSON.parse(requestText.value || "{}")
    return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null
  }
  catch {
    return null
  }
})
const requestValid = computed(() => parsedRequest.value !== null)
const valid = computed(() => Boolean(draft.service_offering_id && parsedRequest.value))

function payload(): ServiceActionDraft {
  return {
    service_offering_id: draft.service_offering_id,
    request_payload: parsedRequest.value || {},
    title: draft.title.trim(),
    description: draft.description.trim(),
    idempotency_key: `service-${nanoid()}`,
  }
}

async function handlePreview() {
  if (!valid.value)
    return
  submitting.value = true
  try {
    previewPayload.value = payload()
    preview.value = await previewServiceAction(props.taskId, previewPayload.value)
  }
  finally {
    submitting.value = false
  }
}

async function handleCreate() {
  if (!preview.value || !previewPayload.value)
    return
  submitting.value = true
  try {
    await createServiceAction(props.taskId, { ...previewPayload.value, preview_digest: preview.value.preview_digest })
    window.$message?.success($t("page.research.serviceRequestCreated"))
    visible.value = false
    emit("created")
  }
  finally {
    submitting.value = false
  }
}

function open() {
  visible.value = true
  if (serviceOptions.value.length === 1)
    draft.service_offering_id = serviceOptions.value[0].value
}

function reset() {
  preview.value = null
  previewPayload.value = null
  requestText.value = "{}"
  draft.service_offering_id = ""
  draft.title = ""
  draft.description = ""
}
</script>

<style scoped>
.service-preview { border: 1px solid rgb(226 232 240); border-radius: 1rem; padding: 1rem; }
pre { overflow: auto; max-height: 18rem; border-radius: 0.75rem; background: rgb(248 250 252); padding: 0.75rem; font-size: 0.75rem; }
</style>

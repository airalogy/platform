<template>
  <section class="resource-library__panel service-catalog" data-testid="research-service-catalog">
    <div class="panel-heading">
      <div>
        <h3>{{ $t("page.resourceLibrary.externalServices") }}</h3>
        <p>{{ $t("page.resourceLibrary.externalServicesHint") }}</p>
      </div>
      <n-button type="primary" @click="openProvider()">
        {{ $t("page.resourceLibrary.addServiceProvider") }}
      </n-button>
    </div>

    <n-alert type="info" class="mb-5">
      {{ $t("page.resourceLibrary.serviceGovernanceHint") }}
    </n-alert>
    <n-spin :show="loading">
      <n-empty
        v-if="!providers.length && !loading"
        :description="$t('page.resourceLibrary.noServiceProviders')"
        class="py-12"
      />
      <div v-else class="space-y-4">
        <n-card v-for="provider in providers" :key="provider.id" size="small">
          <template #header>
            <div class="flex flex-wrap items-center gap-2">
              <span>{{ provider.name }}</span>
              <n-tag size="small" :type="provider.enabled ? 'success' : 'default'">
                {{ provider.enabled ? $t("page.resourceLibrary.enabled") : $t("page.resourceLibrary.disabled") }}
              </n-tag>
              <code class="aira-type-caption aira-text-muted">{{ provider.provider_key }}</code>
            </div>
          </template>
          <template #header-extra>
            <div class="flex gap-2">
              <n-button text type="primary" @click="openOffering(provider)">
                {{ $t("page.resourceLibrary.addServiceOffering") }}
              </n-button>
              <n-button text @click="openProvider(provider)">
                {{ $t("common.edit") }}
              </n-button>
            </div>
          </template>
          <p v-if="provider.description" class="aira-type-body aira-text-secondary mt-0">
            {{ provider.description }}
          </p>
          <div class="mb-4 flex flex-wrap gap-x-5 gap-y-1 aira-type-caption aira-text-muted">
            <span v-if="provider.contact_name">{{ provider.contact_name }}</span>
            <a v-if="provider.contact_email" :href="`mailto:${provider.contact_email}`">{{ provider.contact_email }}</a>
            <a v-if="provider.website_url" :href="provider.website_url" target="_blank" rel="noopener noreferrer">
              {{ $t("page.resourceLibrary.providerWebsite") }}
            </a>
          </div>
          <n-empty
            v-if="!provider.offerings.length"
            :description="$t('page.resourceLibrary.noServiceOfferings')"
            class="py-6"
          />
          <div v-else class="grid grid-cols-1 gap-3 xl:grid-cols-2">
            <article v-for="offering in provider.offerings" :key="offering.source_id" class="service-offering">
              <div class="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <strong class="aira-type-label">{{ offering.name }}</strong>
                  <div class="mt-1 flex flex-wrap gap-2">
                    <n-tag size="small">v{{ offering.version }} · r{{ offering.metadata.offering_revision }}</n-tag>
                    <n-tag size="small" :type="offering.available ? 'success' : 'default'">
                      {{ offering.available ? $t("page.resourceLibrary.enabled") : $t("page.resourceLibrary.disabled") }}
                    </n-tag>
                    <n-tag size="small" :type="offering.risk === 'high' ? 'error' : offering.risk === 'medium' ? 'warning' : 'info'">
                      {{ $t(`page.resourceLibrary.risk.${offering.risk}` as any) }}
                    </n-tag>
                  </div>
                </div>
                <n-button text type="primary" @click="openOffering(provider, offering)">
                  {{ $t("page.resourceLibrary.reviseServiceOffering") }}
                </n-button>
              </div>
              <p class="aira-type-body aira-text-secondary mb-3 mt-3">
                {{ offering.description || $t("page.resourceLibrary.noDescription") }}
              </p>
              <div class="grid grid-cols-1 gap-2 text-sm sm:grid-cols-3">
                <div>
                  <span class="aira-type-caption aira-text-muted">{{ $t("page.resourceLibrary.quotePolicy") }}</span>
                  <div>{{ offering.metadata.quote_required ? $t("page.resourceLibrary.quoteRequired") : $t("page.resourceLibrary.catalogPrice") }}</div>
                </div>
                <div>
                  <span class="aira-type-caption aira-text-muted">{{ $t("page.resourceLibrary.basePrice") }}</span>
                  <div>{{ offering.metadata.base_price ? `${offering.metadata.base_price} ${offering.metadata.currency}` : "-" }}</div>
                </div>
                <div>
                  <span class="aira-type-caption aira-text-muted">{{ $t("page.resourceLibrary.serviceSla") }}</span>
                  <div>{{ offering.metadata.sla_hours ? `${offering.metadata.sla_hours} h` : "-" }}</div>
                </div>
              </div>
            </article>
          </div>
        </n-card>
      </div>
    </n-spin>

    <n-modal
      v-model:show="providerVisible"
      preset="card"
      class="service-modal"
      :title="editingProvider ? $t('page.resourceLibrary.editServiceProvider') : $t('page.resourceLibrary.addServiceProvider')"
      :mask-closable="false"
    >
      <n-form v-if="!providerPreview" label-placement="top">
        <div class="grid grid-cols-1 gap-x-4 md:grid-cols-2">
          <n-form-item :label="$t('page.resourceLibrary.providerKey')" required>
            <n-input v-model:value="providerDraft.provider_key" :disabled="Boolean(editingProvider)" />
          </n-form-item>
          <n-form-item :label="$t('common.name')" required>
            <n-input v-model:value="providerDraft.name" />
          </n-form-item>
        </div>
        <n-form-item :label="$t('common.description')">
          <n-input v-model:value="providerDraft.description" type="textarea" />
        </n-form-item>
        <div class="grid grid-cols-1 gap-x-4 md:grid-cols-2">
          <n-form-item :label="$t('page.resourceLibrary.providerContact')">
            <n-input v-model:value="providerDraft.contact_name" />
          </n-form-item>
          <n-form-item :label="$t('page.resourceLibrary.providerEmail')">
            <n-input v-model:value="providerDraft.contact_email" />
          </n-form-item>
        </div>
        <n-form-item :label="$t('page.resourceLibrary.providerWebsite')">
          <n-input v-model:value="providerDraft.website_url" placeholder="https://" />
        </n-form-item>
        <n-form-item :label="$t('page.resourceLibrary.changeReason')">
          <n-input v-model:value="providerDraft.reason" type="textarea" />
        </n-form-item>
        <n-form-item :label="$t('page.resourceLibrary.enabled')">
          <n-switch v-model:value="providerDraft.enabled" />
        </n-form-item>
      </n-form>
      <div v-else class="space-y-4">
        <n-alert type="warning">{{ $t("page.resourceLibrary.serviceProviderImpact") }}</n-alert>
        <section class="research-preview-card">
          <strong>{{ providerDraft.name }}</strong>
          <div class="aira-type-body aira-text-secondary mt-2">{{ providerDraft.provider_key }}</div>
        </section>
      </div>
      <template #footer>
        <div class="flex justify-end gap-2">
          <n-button @click="providerPreview ? providerPreview = null : (providerVisible = false)">
            {{ providerPreview ? $t("page.research.backToEdit") : $t("common.cancel") }}
          </n-button>
          <n-button type="primary" :loading="saving" :disabled="!providerDraft.name || !providerDraft.provider_key" @click="providerPreview ? saveProvider() : previewProvider()">
            {{ providerPreview ? $t("common.confirm") : $t("common.preview") }}
          </n-button>
        </div>
      </template>
    </n-modal>

    <n-modal
      v-model:show="offeringVisible"
      preset="card"
      class="service-modal service-modal--wide"
      :title="editingOffering ? $t('page.resourceLibrary.reviseServiceOffering') : $t('page.resourceLibrary.addServiceOffering')"
      :mask-closable="false"
    >
      <n-form v-if="!offeringPreview" label-placement="top">
        <div class="grid grid-cols-1 gap-x-4 md:grid-cols-3">
          <n-form-item :label="$t('page.resourceLibrary.offeringKey')" required>
            <n-input v-model:value="offeringDraft.offering_key" :disabled="Boolean(editingOffering)" />
          </n-form-item>
          <n-form-item :label="$t('common.name')" required>
            <n-input v-model:value="offeringDraft.name" />
          </n-form-item>
          <n-form-item :label="$t('page.resourceLibrary.serviceVersion')" required>
            <n-input v-model:value="offeringDraft.service_version" />
          </n-form-item>
        </div>
        <n-form-item :label="$t('common.description')">
          <n-input v-model:value="offeringDraft.description" type="textarea" />
        </n-form-item>
        <div class="grid grid-cols-1 gap-x-4 md:grid-cols-4">
          <n-form-item :label="$t('page.resourceLibrary.riskLevel')">
            <n-select v-model:value="offeringDraft.risk" :options="riskOptions" />
          </n-form-item>
          <n-form-item :label="$t('page.resourceLibrary.basePrice')">
            <n-input v-model:value="offeringDraft.base_price" inputmode="decimal" />
          </n-form-item>
          <n-form-item :label="$t('page.resourceLibrary.serviceCurrency')">
            <n-input v-model:value="offeringDraft.currency" placeholder="USD" />
          </n-form-item>
          <n-form-item :label="$t('page.resourceLibrary.serviceSla')">
            <n-input-number v-model:value="offeringDraft.sla_hours" :min="1" :max="87600" class="w-full" />
          </n-form-item>
        </div>
        <div class="grid grid-cols-1 gap-x-4 md:grid-cols-2">
          <n-form-item :label="$t('page.resourceLibrary.serviceInputSchema')" required :validation-status="jsonError ? 'error' : undefined">
            <n-input v-model:value="inputSchemaText" type="textarea" :autosize="{ minRows: 8, maxRows: 16 }" />
          </n-form-item>
          <n-form-item :label="$t('page.resourceLibrary.serviceResultSchema')" required :validation-status="jsonError ? 'error' : undefined">
            <n-input v-model:value="resultSchemaText" type="textarea" :autosize="{ minRows: 8, maxRows: 16 }" />
          </n-form-item>
        </div>
        <div class="grid grid-cols-1 gap-x-4 md:grid-cols-2">
          <n-form-item :label="$t('page.resourceLibrary.sampleRequirements')" :feedback="jsonError">
            <n-input v-model:value="sampleRequirementsText" type="textarea" :autosize="{ minRows: 5, maxRows: 12 }" />
          </n-form-item>
          <n-form-item :label="$t('page.resourceLibrary.logisticsPolicy')">
            <n-input v-model:value="logisticsPolicyText" type="textarea" :autosize="{ minRows: 5, maxRows: 12 }" />
          </n-form-item>
        </div>
        <n-form-item :label="$t('page.resourceLibrary.serviceTerms')">
          <n-input v-model:value="offeringDraft.terms" type="textarea" />
        </n-form-item>
        <n-form-item :label="$t('page.resourceLibrary.changeReason')">
          <n-input v-model:value="offeringDraft.reason" type="textarea" />
        </n-form-item>
        <div class="flex flex-wrap gap-6">
          <n-checkbox v-model:checked="offeringDraft.quote_required">{{ $t("page.resourceLibrary.quoteRequired") }}</n-checkbox>
          <n-checkbox v-model:checked="offeringDraft.enabled">{{ $t("page.resourceLibrary.enabled") }}</n-checkbox>
        </div>
      </n-form>
      <div v-else class="space-y-4">
        <n-alert type="warning">{{ $t("page.resourceLibrary.serviceOfferingImpact") }}</n-alert>
        <section class="research-preview-card">
          <strong>{{ offeringDraft.name }} · v{{ offeringDraft.service_version }}</strong>
          <div class="aira-type-body aira-text-secondary mt-2">
            {{ selectedProvider?.name }} · {{ offeringDraft.offering_key }}
          </div>
        </section>
      </div>
      <template #footer>
        <div class="flex justify-end gap-2">
          <n-button @click="offeringPreview ? offeringPreview = null : (offeringVisible = false)">
            {{ offeringPreview ? $t("page.research.backToEdit") : $t("common.cancel") }}
          </n-button>
          <n-button type="primary" :loading="saving" :disabled="!offeringDraft.name || !offeringDraft.offering_key || !offeringDraft.service_version" @click="offeringPreview ? saveOffering() : previewOffering()">
            {{ offeringPreview ? $t("common.confirm") : $t("common.preview") }}
          </n-button>
        </div>
      </template>
    </n-modal>
  </section>
</template>

<script setup lang="ts">
import type {
  ResearchServiceOffering,
  ResearchServicePreview,
  ResearchServiceProvider,
  ServiceOfferingDraft,
  ServiceOfferingRevisionDraft,
  ServiceProviderDraft,
  ServiceProviderUpdateDraft,
} from "@/service/api/research-services"
import {
  createServiceOffering,
  createServiceOfferingRevision,
  createServiceProvider,
  fetchResearchServices,
  previewServiceOffering,
  previewServiceOfferingRevision,
  previewServiceProvider,
  previewServiceProviderUpdate,
  updateServiceProvider,
} from "@/service/api/research-services"
import { $t } from "@airalogy/shared/locales"

const props = defineProps<{ labId: string }>()

const loading = ref(false)
const saving = ref(false)
const providers = ref<ResearchServiceProvider[]>([])
const providerVisible = ref(false)
const offeringVisible = ref(false)
const editingProvider = ref<ResearchServiceProvider | null>(null)
const editingOffering = ref<ResearchServiceOffering | null>(null)
const selectedProvider = ref<ResearchServiceProvider | null>(null)
const providerPreview = ref<ResearchServicePreview | null>(null)
const offeringPreview = ref<ResearchServicePreview | null>(null)
const jsonError = ref("")
const inputSchemaText = ref("")
const resultSchemaText = ref("")
const sampleRequirementsText = ref("")
const logisticsPolicyText = ref("")

const providerDraft = reactive<ServiceProviderDraft>({
  lab_id: "",
  provider_key: "",
  name: "",
  description: "",
  contact_name: "",
  contact_email: "",
  website_url: "",
  enabled: true,
  reason: "",
})
const offeringDraft = reactive({
  provider_id: "",
  offering_key: "",
  name: "",
  description: "",
  service_version: "1",
  quote_required: true,
  base_price: "",
  currency: "USD",
  sla_hours: null as number | null,
  terms: "",
  risk: "medium" as ServiceOfferingDraft["risk"],
  enabled: true,
  reason: "",
})
const riskOptions = computed(() => (["low", "medium", "high"] as const).map(value => ({
  label: $t(`page.resourceLibrary.risk.${value}` as any),
  value,
})))

async function load() {
  if (!props.labId)
    return
  loading.value = true
  try {
    providers.value = (await fetchResearchServices(props.labId)).providers
  }
  finally {
    loading.value = false
  }
}

function openProvider(provider?: ResearchServiceProvider) {
  editingProvider.value = provider || null
  providerPreview.value = null
  Object.assign(providerDraft, provider
    ? {
        lab_id: provider.lab_id,
        provider_key: provider.provider_key,
        name: provider.name,
        description: provider.description,
        contact_name: provider.contact_name,
        contact_email: provider.contact_email,
        website_url: provider.website_url,
        enabled: provider.enabled,
        reason: "",
      }
    : {
        lab_id: props.labId,
        provider_key: "",
        name: "",
        description: "",
        contact_name: "",
        contact_email: "",
        website_url: "",
        enabled: true,
        reason: "",
      })
  providerVisible.value = true
}

function providerPayload(): ServiceProviderDraft | ServiceProviderUpdateDraft {
  if (editingProvider.value) {
    return {
      expected_revision: editingProvider.value.revision,
      name: providerDraft.name,
      description: providerDraft.description,
      contact_name: providerDraft.contact_name,
      contact_email: providerDraft.contact_email,
      website_url: providerDraft.website_url,
      enabled: providerDraft.enabled,
      reason: providerDraft.reason,
    }
  }
  return { ...providerDraft }
}

async function previewProvider() {
  saving.value = true
  try {
    providerPreview.value = editingProvider.value
      ? await previewServiceProviderUpdate(editingProvider.value.id, providerPayload() as ServiceProviderUpdateDraft)
      : await previewServiceProvider(providerPayload() as ServiceProviderDraft)
  }
  finally {
    saving.value = false
  }
}

async function saveProvider() {
  if (!providerPreview.value)
    return
  saving.value = true
  try {
    if (editingProvider.value) {
      await updateServiceProvider(editingProvider.value.id, {
        ...(providerPayload() as ServiceProviderUpdateDraft),
        preview_digest: providerPreview.value.preview_digest,
      })
    }
    else {
      await createServiceProvider({
        ...(providerPayload() as ServiceProviderDraft),
        preview_digest: providerPreview.value.preview_digest,
      })
    }
    providerVisible.value = false
    window.$message?.success($t("page.resourceLibrary.serviceProviderSaved"))
    await load()
  }
  finally {
    saving.value = false
  }
}

function pretty(value: unknown) {
  return JSON.stringify(value, null, 2)
}

function openOffering(provider: ResearchServiceProvider, offering?: ResearchServiceOffering) {
  selectedProvider.value = provider
  editingOffering.value = offering || null
  offeringPreview.value = null
  jsonError.value = ""
  Object.assign(offeringDraft, offering
    ? {
        provider_id: provider.id,
        offering_key: offering.metadata.offering_key,
        name: offering.name,
        description: offering.description,
        service_version: offering.version,
        quote_required: offering.metadata.quote_required,
        base_price: offering.metadata.base_price || "",
        currency: offering.metadata.currency || "USD",
        sla_hours: offering.metadata.sla_hours || null,
        terms: offering.metadata.terms,
        risk: offering.risk,
        enabled: offering.metadata.offering_enabled,
        reason: "",
      }
    : {
        provider_id: provider.id,
        offering_key: "",
        name: "",
        description: "",
        service_version: "1",
        quote_required: true,
        base_price: "",
        currency: "USD",
        sla_hours: null,
        terms: "",
        risk: "medium",
        enabled: true,
        reason: "",
      })
  inputSchemaText.value = pretty(offering?.input_schema || { type: "object", properties: {}, additionalProperties: false })
  resultSchemaText.value = pretty(offering?.output_schema || { type: "object", properties: {}, additionalProperties: false })
  sampleRequirementsText.value = pretty(offering?.metadata.sample_requirements || {})
  logisticsPolicyText.value = pretty(offering?.metadata.logistics_policy || {})
  offeringVisible.value = true
}

function parseObject(text: string, label: string) {
  const value = JSON.parse(text)
  if (!value || Array.isArray(value) || typeof value !== "object")
    throw new Error(`${label} must be a JSON object`)
  return value as Record<string, any>
}

function offeringPayload(): ServiceOfferingDraft | ServiceOfferingRevisionDraft {
  jsonError.value = ""
  try {
    const payload: ServiceOfferingDraft = {
      ...offeringDraft,
      base_price: offeringDraft.base_price.trim() || null,
      currency: offeringDraft.base_price.trim() ? offeringDraft.currency.trim().toUpperCase() : null,
      input_schema: parseObject(inputSchemaText.value, "Input Schema"),
      result_schema: parseObject(resultSchemaText.value, "Result Schema"),
      sample_requirements: parseObject(sampleRequirementsText.value, "Sample requirements"),
      logistics_policy: parseObject(logisticsPolicyText.value, "Logistics policy"),
    }
    return editingOffering.value
      ? { ...payload, expected_revision: editingOffering.value.metadata.offering_revision }
      : payload
  }
  catch (error) {
    jsonError.value = error instanceof Error ? error.message : String(error)
    throw error
  }
}

async function previewOfferingAction() {
  const payload = offeringPayload()
  return editingOffering.value
    ? previewServiceOfferingRevision(editingOffering.value.source_id, payload as ServiceOfferingRevisionDraft)
    : previewServiceOffering(payload as ServiceOfferingDraft)
}

async function previewOffering() {
  saving.value = true
  try {
    offeringPreview.value = await previewOfferingAction()
  }
  catch (error) {
    if (!jsonError.value)
      throw error
  }
  finally {
    saving.value = false
  }
}

async function saveOffering() {
  if (!offeringPreview.value)
    return
  saving.value = true
  try {
    const payload = offeringPayload()
    if (editingOffering.value) {
      await createServiceOfferingRevision(editingOffering.value.source_id, {
        ...(payload as ServiceOfferingRevisionDraft),
        preview_digest: offeringPreview.value.preview_digest,
      })
    }
    else {
      await createServiceOffering({
        ...(payload as ServiceOfferingDraft),
        preview_digest: offeringPreview.value.preview_digest,
      })
    }
    offeringVisible.value = false
    window.$message?.success($t("page.resourceLibrary.serviceOfferingSaved"))
    await load()
  }
  finally {
    saving.value = false
  }
}

watch(() => props.labId, () => void load(), { immediate: true })
</script>

<style scoped>
.service-catalog :deep(.n-card-header) {
  align-items: flex-start;
}

.service-offering {
  border: 1px solid var(--n-border-color);
  border-radius: 12px;
  padding: 16px;
}

:global(.service-modal) {
  width: min(680px, calc(100vw - 32px));
}

:global(.service-modal--wide) {
  width: min(980px, calc(100vw - 32px));
}
</style>

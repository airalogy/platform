<template>
  <section class="instrument-gateways">
    <div class="panel-heading">
      <div>
        <h3>{{ $t("page.resourceLibrary.instrumentGateways") }}</h3>
        <p>{{ $t("page.resourceLibrary.instrumentGatewaysHint") }}</p>
      </div>
      <n-button type="primary" @click="openGatewayCreate">
        {{ $t("page.resourceLibrary.addInstrumentGateway") }}
      </n-button>
    </div>

    <n-alert type="info" :bordered="false" class="mb-4">
      {{ $t("page.resourceLibrary.instrumentGatewaySecurityHint") }}
    </n-alert>

    <div v-if="gateways.length" class="gateway-grid">
      <article
        v-for="gateway in gateways"
        :key="gateway.id"
        class="gateway-card"
        :class="{ 'gateway-card--selected': gateway.id === selectedGatewayId }"
      >
        <button type="button" class="gateway-card__main" @click="selectGateway(gateway)">
          <span class="gateway-card__heading">
            <strong>{{ gateway.name }}</strong>
            <n-tag :type="gateway.enabled ? 'success' : 'default'" size="small">
              {{
                gateway.enabled
                  ? $t("page.resourceLibrary.enabled")
                  : $t("page.resourceLibrary.disabled")
              }}
            </n-tag>
          </span>
          <span>{{ gateway.description || $t("page.resourceLibrary.noDescription") }}</span>
          <small>
            {{ $t("page.resourceLibrary.credentialHint", { hint: gateway.token_hint }) }}
            ·
            {{
              gateway.last_seen_at
                ? formatDate(gateway.last_seen_at)
                : $t("page.resourceLibrary.neverConnected")
            }}
          </small>
        </button>
        <n-space size="small">
          <n-button size="small" secondary @click="openGatewayEdit(gateway)">
            {{ $t("common.edit") }}
          </n-button>
          <n-button size="small" secondary @click="openCredentialRotation(gateway)">
            {{ $t("page.resourceLibrary.rotateCredential") }}
          </n-button>
        </n-space>
      </article>
    </div>
    <n-empty
      v-else-if="!loading"
      :description="$t('page.resourceLibrary.noInstrumentGateways')"
      class="py-12"
    />

    <section v-if="selectedGateway" class="command-panel">
      <div class="panel-heading">
        <div>
          <h3>{{ $t("page.resourceLibrary.allowedCommands") }}</h3>
          <p>
            {{
              $t("page.resourceLibrary.allowedCommandsHint", { gateway: selectedGateway.name })
            }}
          </p>
        </div>
        <n-button type="primary" :disabled="!selectedGateway.enabled" @click="openCommandCreate">
          {{ $t("page.resourceLibrary.addAllowedCommand") }}
        </n-button>
      </div>
      <n-data-table
        :columns="commandColumns"
        :data="commands"
        :bordered="false"
        :single-line="false"
        :scroll-x="980"
      />
      <n-empty
        v-if="!commands.length && !loadingCommands"
        :description="$t('page.resourceLibrary.noAllowedCommands')"
        class="py-12"
      />
    </section>

    <n-modal
      v-model:show="gatewayModalVisible"
      preset="dialog"
      :title="
        editingGateway
          ? $t('page.resourceLibrary.editInstrumentGateway')
          : $t('page.resourceLibrary.addInstrumentGateway')
      "
      :show-icon="false"
      :mask-closable="false"
    >
      <n-form label-placement="top">
        <n-form-item :label="$t('common.name')" required>
          <n-input v-model:value="gatewayDraft.name" :disabled="!!gatewayPreview" />
        </n-form-item>
        <n-form-item :label="$t('common.description')">
          <n-input
            v-model:value="gatewayDraft.description"
            type="textarea"
            :disabled="!!gatewayPreview"
          />
        </n-form-item>
        <n-form-item :label="$t('common.status')">
          <n-switch v-model:value="gatewayDraft.enabled" :disabled="!!gatewayPreview">
            <template #checked>
              {{ $t("common.enabled") }}
            </template>
            <template #unchecked>
              {{ $t("common.disabled") }}
            </template>
          </n-switch>
        </n-form-item>
        <n-form-item :label="$t('page.resourceLibrary.changeReason')">
          <n-input v-model:value="gatewayDraft.reason" :disabled="!!gatewayPreview" />
        </n-form-item>
        <n-alert v-if="gatewayPreview" type="warning" :bordered="false">
          {{
            editingGateway
              ? $t("page.resourceLibrary.gatewayUpdateImpact")
              : $t("page.resourceLibrary.gatewayCreateImpact")
          }}
        </n-alert>
      </n-form>
      <template #action>
        <n-button v-if="gatewayPreview" @click="gatewayPreview = null">
          {{ $t("common.previous") }}
        </n-button>
        <n-button v-else @click="gatewayModalVisible = false">
          {{ $t("common.cancel") }}
        </n-button>
        <n-button v-if="!gatewayPreview" type="primary" :loading="saving" @click="previewGateway">
          {{ $t("common.preview") }}
        </n-button>
        <n-button v-else type="primary" :loading="saving" @click="confirmGateway">
          {{ $t("common.confirm") }}
        </n-button>
      </template>
    </n-modal>

    <n-modal
      v-model:show="rotationModalVisible"
      preset="dialog"
      :title="$t('page.resourceLibrary.rotateCredential')"
      :show-icon="false"
      :mask-closable="false"
    >
      <n-alert type="warning" :bordered="false" class="mb-4">
        {{ $t("page.resourceLibrary.rotateCredentialImpact") }}
      </n-alert>
      <n-form label-placement="top">
        <n-form-item :label="$t('page.resourceLibrary.changeReason')" required>
          <n-input v-model:value="rotationReason" :disabled="!!rotationPreview" />
        </n-form-item>
      </n-form>
      <template #action>
        <n-button v-if="rotationPreview" @click="rotationPreview = null">
          {{ $t("common.previous") }}
        </n-button>
        <n-button v-else @click="rotationModalVisible = false">
          {{ $t("common.cancel") }}
        </n-button>
        <n-button v-if="!rotationPreview" type="warning" :loading="saving" @click="previewRotation">
          {{ $t("common.preview") }}
        </n-button>
        <n-button v-else type="warning" :loading="saving" @click="confirmRotation">
          {{ $t("common.confirm") }}
        </n-button>
      </template>
    </n-modal>

    <n-modal
      v-model:show="credentialModalVisible"
      preset="dialog"
      :title="$t('page.resourceLibrary.gatewayCredential')"
      :show-icon="false"
      :mask-closable="false"
      :close-on-esc="false"
    >
      <n-alert type="warning" class="mb-4">
        {{ $t("page.resourceLibrary.gatewayCredentialOnce") }}
      </n-alert>
      <n-input :value="issuedCredential" readonly type="textarea" :rows="3" />
      <template #action>
        <n-button secondary @click="copyCredential">
          {{ $t("page.resourceLibrary.copyCredential") }}
        </n-button>
        <n-button type="primary" @click="closeCredential">
          {{ $t("common.close") }}
        </n-button>
      </template>
    </n-modal>

    <n-modal
      v-model:show="commandModalVisible"
      preset="dialog"
      :title="
        editingCommand
          ? $t('page.resourceLibrary.editAllowedCommand')
          : $t('page.resourceLibrary.addAllowedCommand')
      "
      :show-icon="false"
      :mask-closable="false"
      class="instrument-command-dialog"
    >
      <n-form label-placement="top">
        <n-form-item v-if="!editingCommand" :label="$t('page.resourceLibrary.equipment')" required>
          <n-select
            v-model:value="commandDraft.resource_id"
            filterable
            :options="equipmentOptions"
            :disabled="!!commandPreview"
          />
        </n-form-item>
        <div class="form-grid">
          <n-form-item :label="$t('page.resourceLibrary.commandKey')" required>
            <n-input
              v-model:value="commandDraft.command_key"
              :disabled="!!editingCommand || !!commandPreview"
            />
          </n-form-item>
          <n-form-item :label="$t('page.resourceLibrary.commandVersion')" required>
            <n-input
              v-model:value="commandDraft.command_version"
              :disabled="!!editingCommand || !!commandPreview"
            />
          </n-form-item>
        </div>
        <n-form-item :label="$t('common.name')" required>
          <n-input v-model:value="commandDraft.name" :disabled="!!commandPreview" />
        </n-form-item>
        <n-form-item :label="$t('common.description')">
          <n-input
            v-model:value="commandDraft.description"
            type="textarea"
            :disabled="!!commandPreview"
          />
        </n-form-item>
        <div class="form-grid">
          <n-form-item :label="$t('page.resourceLibrary.riskLevel')">
            <n-select
              v-model:value="commandDraft.risk"
              :options="riskOptions"
              :disabled="!!commandPreview"
            />
          </n-form-item>
          <n-form-item :label="$t('page.resourceLibrary.commandTimeout')">
            <n-input-number
              v-model:value="commandDraft.timeout_seconds"
              :min="1"
              :max="86400"
              :disabled="!!commandPreview"
              class="w-full"
            />
          </n-form-item>
        </div>
        <n-checkbox
          v-model:checked="commandDraft.device_confirmation_required"
          :disabled="!!commandPreview"
        >
          {{ $t("page.resourceLibrary.deviceConfirmationRequired") }}
        </n-checkbox>
        <div class="form-grid mt-4">
          <n-form-item
            :label="$t('page.resourceLibrary.inputSchema')"
            :feedback="commandJsonError"
            :validation-status="commandJsonError ? 'error' : undefined"
          >
            <n-input
              v-model:value="commandDraft.input_schema"
              type="textarea"
              :rows="8"
              :disabled="!!commandPreview"
            />
          </n-form-item>
          <n-form-item
            :label="$t('page.resourceLibrary.outputSchema')"
            :feedback="commandJsonError"
            :validation-status="commandJsonError ? 'error' : undefined"
          >
            <n-input
              v-model:value="commandDraft.output_schema"
              type="textarea"
              :rows="8"
              :disabled="!!commandPreview"
            />
          </n-form-item>
        </div>
        <n-form-item :label="$t('page.resourceLibrary.changeReason')">
          <n-input v-model:value="commandDraft.reason" :disabled="!!commandPreview" />
        </n-form-item>
        <n-alert v-if="commandPreview" type="warning" :bordered="false">
          {{ $t("page.resourceLibrary.commandChangeImpact") }}
        </n-alert>
      </n-form>
      <template #action>
        <n-button v-if="commandPreview" @click="commandPreview = null">
          {{ $t("common.previous") }}
        </n-button>
        <n-button v-else @click="commandModalVisible = false">
          {{ $t("common.cancel") }}
        </n-button>
        <n-button v-if="!commandPreview" type="primary" :loading="saving" @click="previewCommand">
          {{ $t("common.preview") }}
        </n-button>
        <n-button v-else type="primary" :loading="saving" @click="confirmCommand">
          {{ $t("common.confirm") }}
        </n-button>
      </template>
    </n-modal>
  </section>
</template>

<script setup lang="ts">
import type {
  InstrumentCommand,
  InstrumentCommandPayload,
  InstrumentCommandUpdatePayload,
  InstrumentGateway,
  InstrumentPreview,
} from "@/service/api/research-instruments"
import type { DataTableColumns } from "naive-ui"
import {
  createInstrumentCommand,
  createInstrumentGateway,
  fetchInstrumentCommands,
  fetchInstrumentGateways,
  previewGatewayCredentialRotation,
  previewInstrumentCommand,
  previewInstrumentCommandUpdate,
  previewInstrumentGateway,
  previewInstrumentGatewayUpdate,
  rotateGatewayCredential,
  updateInstrumentCommand,
  updateInstrumentGateway,
} from "@/service/api/research-instruments"
import { $t } from "@airalogy/shared/locales"
import { NButton, NSpace, NTag } from "naive-ui"

const props = defineProps<{
  labId: string
  equipmentOptions: Array<{ label: string, value: string }>
}>()

const loading = ref(false)
const loadingCommands = ref(false)
const saving = ref(false)
const gateways = ref<InstrumentGateway[]>([])
const commands = ref<InstrumentCommand[]>([])
const selectedGatewayId = ref<string | null>(null)
const selectedGateway = computed(
  () => gateways.value.find(item => item.id === selectedGatewayId.value) || null,
)

const gatewayModalVisible = ref(false)
const editingGateway = ref<InstrumentGateway | null>(null)
const gatewayPreview = ref<InstrumentPreview | null>(null)
const gatewayDraft = reactive({ name: "", description: "", enabled: true, reason: "" })

const rotationModalVisible = ref(false)
const rotatingGateway = ref<InstrumentGateway | null>(null)
const rotationReason = ref("")
const rotationPreview = ref<InstrumentPreview | null>(null)

const credentialModalVisible = ref(false)
const issuedCredential = ref("")

const commandModalVisible = ref(false)
const editingCommand = ref<InstrumentCommand | null>(null)
const commandPreview = ref<InstrumentPreview | null>(null)
const commandJsonError = ref("")
const objectSchema
  = "{\n  \"type\": \"object\",\n  \"properties\": {},\n  \"additionalProperties\": false\n}"
const commandDraft = reactive({
  resource_id: null as string | null,
  command_key: "",
  command_version: "1",
  name: "",
  description: "",
  input_schema: objectSchema,
  output_schema: objectSchema,
  risk: "medium" as InstrumentCommand["risk"],
  device_confirmation_required: true,
  timeout_seconds: 3600,
  enabled: true,
  reason: "",
})

const riskOptions = computed(() =>
  ["read_only", "low", "medium", "high"].map(value => ({
    value,
    label: $t(`page.resourceLibrary.risk.${value}` as any),
  })),
)

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(
    new Date(value),
  )
}

function resourceName(resourceId: string) {
  return props.equipmentOptions.find(item => item.value === resourceId)?.label || resourceId
}

function riskType(risk: InstrumentCommand["risk"]) {
  if (risk === "high")
    return "error"
  if (risk === "medium")
    return "warning"
  if (risk === "low")
    return "info"
  return "default"
}

const commandColumns: DataTableColumns<InstrumentCommand> = [
  {
    title: $t("common.name"),
    key: "name",
    minWidth: 180,
    render: row =>
      h("div", [
        h("strong", row.name),
        h("small", { class: "block text-secondary" }, `${row.command_key}@${row.command_version}`),
      ]),
  },
  {
    title: $t("page.resourceLibrary.equipment"),
    key: "resource_id",
    minWidth: 180,
    render: row => resourceName(row.resource_id),
  },
  {
    title: $t("page.resourceLibrary.riskLevel"),
    key: "risk",
    width: 130,
    render: row =>
      h(
        NTag,
        { size: "small", type: riskType(row.risk) },
        { default: () => $t(`page.resourceLibrary.risk.${row.risk}` as any) },
      ),
  },
  {
    title: $t("common.status"),
    key: "enabled",
    width: 110,
    render: row =>
      h(
        NTag,
        { size: "small", type: row.enabled ? "success" : "default" },
        {
          default: () =>
            row.enabled ? $t("page.resourceLibrary.enabled") : $t("page.resourceLibrary.disabled"),
        },
      ),
  },
  {
    title: $t("common.action"),
    key: "actions",
    width: 190,
    render: row =>
      h(
        NSpace,
        { size: "small" },
        {
          default: () => [
            h(
              NButton,
              { size: "small", secondary: true, onClick: () => openCommandEdit(row) },
              { default: () => $t("common.edit") },
            ),
            h(
              NButton,
              { size: "small", secondary: true, onClick: () => toggleCommand(row) },
              {
                default: () =>
                  row.enabled
                    ? $t("page.resourceLibrary.disable")
                    : $t("page.resourceLibrary.enable"),
              },
            ),
          ],
        },
      ),
  },
]

async function loadGateways() {
  if (!props.labId)
    return
  loading.value = true
  try {
    gateways.value = (await fetchInstrumentGateways(props.labId)).items
    if (
      selectedGatewayId.value
      && !gateways.value.some(item => item.id === selectedGatewayId.value)
    ) {
      selectedGatewayId.value = null
    }
    if (!selectedGatewayId.value && gateways.value.length)
      selectedGatewayId.value = gateways.value[0].id
    await loadCommands()
  }
  finally {
    loading.value = false
  }
}

async function loadCommands() {
  if (!selectedGatewayId.value) {
    commands.value = []
    return
  }
  loadingCommands.value = true
  try {
    commands.value = (await fetchInstrumentCommands(selectedGatewayId.value)).items
  }
  finally {
    loadingCommands.value = false
  }
}

async function selectGateway(gateway: InstrumentGateway) {
  selectedGatewayId.value = gateway.id
  await loadCommands()
}

function resetGatewayDraft(gateway?: InstrumentGateway) {
  editingGateway.value = gateway || null
  gatewayDraft.name = gateway?.name || ""
  gatewayDraft.description = gateway?.description || ""
  gatewayDraft.enabled = gateway?.enabled ?? true
  gatewayDraft.reason = ""
  gatewayPreview.value = null
}

function openGatewayCreate() {
  resetGatewayDraft()
  gatewayModalVisible.value = true
}

function openGatewayEdit(gateway: InstrumentGateway) {
  resetGatewayDraft(gateway)
  gatewayModalVisible.value = true
}

async function previewGateway() {
  if (!gatewayDraft.name.trim())
    return
  saving.value = true
  try {
    gatewayPreview.value = editingGateway.value
      ? await previewInstrumentGatewayUpdate(editingGateway.value.id, {
        expected_revision: editingGateway.value.revision,
        ...gatewayDraft,
      })
      : await previewInstrumentGateway({ lab_id: props.labId, ...gatewayDraft })
  }
  finally {
    saving.value = false
  }
}

async function confirmGateway() {
  if (!gatewayPreview.value)
    return
  saving.value = true
  try {
    if (editingGateway.value) {
      await updateInstrumentGateway(editingGateway.value.id, {
        expected_revision: editingGateway.value.revision,
        ...gatewayDraft,
        preview_digest: gatewayPreview.value.preview_digest,
      })
      gatewayModalVisible.value = false
    }
    else {
      const response = await createInstrumentGateway({
        lab_id: props.labId,
        ...gatewayDraft,
        preview_digest: gatewayPreview.value.preview_digest,
      })
      issuedCredential.value = response.credential
      selectedGatewayId.value = response.gateway.id
      gatewayModalVisible.value = false
      credentialModalVisible.value = true
    }
    await loadGateways()
  }
  finally {
    saving.value = false
  }
}

function openCredentialRotation(gateway: InstrumentGateway) {
  rotatingGateway.value = gateway
  rotationReason.value = ""
  rotationPreview.value = null
  rotationModalVisible.value = true
}

async function previewRotation() {
  if (!rotatingGateway.value || !rotationReason.value.trim())
    return
  saving.value = true
  try {
    rotationPreview.value = await previewGatewayCredentialRotation(rotatingGateway.value.id, {
      expected_revision: rotatingGateway.value.revision,
      reason: rotationReason.value,
    })
  }
  finally {
    saving.value = false
  }
}

async function confirmRotation() {
  if (!rotatingGateway.value || !rotationPreview.value)
    return
  saving.value = true
  try {
    const response = await rotateGatewayCredential(rotatingGateway.value.id, {
      expected_revision: rotatingGateway.value.revision,
      reason: rotationReason.value,
      preview_digest: rotationPreview.value.preview_digest,
    })
    issuedCredential.value = response.credential
    rotationModalVisible.value = false
    credentialModalVisible.value = true
    await loadGateways()
  }
  finally {
    saving.value = false
  }
}

async function copyCredential() {
  await navigator.clipboard.writeText(issuedCredential.value)
  window.$message?.success($t("page.resourceLibrary.credentialCopied"))
}

function closeCredential() {
  issuedCredential.value = ""
  credentialModalVisible.value = false
}

function resetCommandDraft(command?: InstrumentCommand) {
  editingCommand.value = command || null
  commandDraft.resource_id = command?.resource_id || null
  commandDraft.command_key = command?.command_key || ""
  commandDraft.command_version = command?.command_version || "1"
  commandDraft.name = command?.name || ""
  commandDraft.description = command?.description || ""
  commandDraft.input_schema = JSON.stringify(
    command?.input_schema || JSON.parse(objectSchema),
    null,
    2,
  )
  commandDraft.output_schema = JSON.stringify(
    command?.output_schema || JSON.parse(objectSchema),
    null,
    2,
  )
  commandDraft.risk = command?.risk || "medium"
  commandDraft.device_confirmation_required = command?.device_confirmation_required ?? true
  commandDraft.timeout_seconds = command?.timeout_seconds || 3600
  commandDraft.enabled = command?.enabled ?? true
  commandDraft.reason = ""
  commandPreview.value = null
  commandJsonError.value = ""
}

function openCommandCreate() {
  resetCommandDraft()
  commandModalVisible.value = true
}

function openCommandEdit(command: InstrumentCommand) {
  resetCommandDraft(command)
  commandModalVisible.value = true
}

function parsedCommandPayload(): InstrumentCommandPayload | InstrumentCommandUpdatePayload | null {
  try {
    const common = {
      name: commandDraft.name,
      description: commandDraft.description,
      input_schema: JSON.parse(commandDraft.input_schema),
      output_schema: JSON.parse(commandDraft.output_schema),
      risk: commandDraft.risk,
      device_confirmation_required: commandDraft.device_confirmation_required,
      timeout_seconds: commandDraft.timeout_seconds,
      enabled: commandDraft.enabled,
      reason: commandDraft.reason,
    }
    commandJsonError.value = ""
    if (editingCommand.value) {
      return {
        expected_revision: editingCommand.value.revision,
        ...common,
      }
    }
    if (!selectedGateway.value || !commandDraft.resource_id)
      return null
    return {
      gateway_id: selectedGateway.value.id,
      resource_id: commandDraft.resource_id,
      command_key: commandDraft.command_key,
      command_version: commandDraft.command_version,
      ...common,
    }
  }
  catch {
    commandJsonError.value = $t("page.resourceLibrary.invalidJson")
    return null
  }
}

async function previewCommand() {
  const payload = parsedCommandPayload()
  if (!payload || !commandDraft.name.trim())
    return
  saving.value = true
  try {
    commandPreview.value = editingCommand.value
      ? await previewInstrumentCommandUpdate(
        editingCommand.value.id,
        payload as InstrumentCommandUpdatePayload,
      )
      : await previewInstrumentCommand(payload as InstrumentCommandPayload)
  }
  finally {
    saving.value = false
  }
}

async function confirmCommand() {
  const payload = parsedCommandPayload()
  if (!payload || !commandPreview.value)
    return
  saving.value = true
  try {
    if (editingCommand.value) {
      await updateInstrumentCommand(editingCommand.value.id, {
        ...(payload as InstrumentCommandUpdatePayload),
        preview_digest: commandPreview.value.preview_digest,
      })
    }
    else {
      await createInstrumentCommand({
        ...(payload as InstrumentCommandPayload),
        preview_digest: commandPreview.value.preview_digest,
      })
    }
    commandModalVisible.value = false
    await loadCommands()
  }
  finally {
    saving.value = false
  }
}

async function toggleCommand(command: InstrumentCommand) {
  const payload: InstrumentCommandUpdatePayload = {
    expected_revision: command.revision,
    name: command.name,
    description: command.description,
    input_schema: command.input_schema,
    output_schema: command.output_schema,
    risk: command.risk,
    device_confirmation_required: command.device_confirmation_required,
    timeout_seconds: command.timeout_seconds,
    enabled: !command.enabled,
    reason: command.enabled
      ? "Disabled from Instrument Gateway manager"
      : "Enabled from Instrument Gateway manager",
  }
  const preview = await previewInstrumentCommandUpdate(command.id, payload)
  window.$dialog?.warning({
    title: command.enabled ? $t("page.resourceLibrary.disable") : $t("page.resourceLibrary.enable"),
    content: $t("page.resourceLibrary.commandToggleImpact"),
    positiveText: $t("common.confirm"),
    negativeText: $t("common.cancel"),
    async onPositiveClick() {
      await updateInstrumentCommand(command.id, {
        ...payload,
        preview_digest: preview.preview_digest,
      })
      await loadCommands()
    },
  })
}

watch(() => props.labId, loadGateways, { immediate: true })
</script>

<style scoped>
.instrument-gateways {
  display: grid;
  gap: 16px;
}

.panel-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.panel-heading h3,
.panel-heading p {
  margin: 0;
}

.panel-heading p {
  margin-top: 4px;
  color: #7b8494;
}

.gateway-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 12px;
}

.gateway-card {
  display: grid;
  gap: 12px;
  padding: 16px;
  border: 1px solid #e7ebf2;
  border-radius: 12px;
  background: #fff;
}

.gateway-card--selected {
  border-color: rgb(var(--primary-color) / 55%);
  box-shadow: 0 0 0 1px rgb(var(--primary-color) / 12%);
}

.gateway-card__main {
  display: grid;
  gap: 6px;
  padding: 0;
  border: 0;
  color: inherit;
  text-align: left;
  background: transparent;
  cursor: pointer;
}

.gateway-card__heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.gateway-card__main small,
.gateway-card__main > span:not(.gateway-card__heading) {
  color: #7b8494;
}

.command-panel {
  display: grid;
  gap: 16px;
  margin-top: 8px;
  padding-top: 20px;
  border-top: 1px solid #e7ebf2;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

@media (max-width: 720px) {
  .panel-heading,
  .gateway-card__heading {
    align-items: stretch;
    flex-direction: column;
  }

  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>

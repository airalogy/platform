<template>
  <div class="flex flex-wrap items-center gap-2">
    <n-tag type="info" size="small" :bordered="false">
      {{ t("page.protocol.schemaGovernance.originalVersion", { version: sourceVersion }) }}
    </n-tag>
    <template v-if="targetOptions.length > 0">
      <n-select
        v-model:value="targetVersion"
        size="small"
        class="w-34"
        :options="targetOptions"
        :placeholder="t('page.protocol.schemaGovernance.targetVersion')"
      />
      <n-button
        size="small"
        secondary
        :loading="loadingAction === 'projection'"
        :disabled="!targetVersion || !!loadingAction"
        @click="openProjection"
      >
        {{ t("page.protocol.schemaGovernance.project") }}
      </n-button>
      <n-button
        v-if="allowMigration"
        size="small"
        type="primary"
        secondary
        :loading="loadingAction === 'migration'"
        :disabled="!targetVersion || !!loadingAction"
        @click="openMigration"
      >
        {{ t("page.protocol.schemaGovernance.migrate") }}
      </n-button>
      <n-tooltip>
        <template #trigger>
          <n-icon size="17" class="text-gray-400">
            <icon-tabler-info-circle />
          </n-icon>
        </template>
        {{ t("page.protocol.schemaGovernance.help") }}
      </n-tooltip>
    </template>
    <span v-else-if="!loadingVersions" class="text-xs text-gray-400">
      {{ t("page.protocol.schemaGovernance.currentOnly") }}
    </span>

    <n-modal
      v-model:show="showModal"
      preset="card"
      class="max-w-4xl w-[calc(100vw-2rem)]"
      :title="modalTitle"
      :mask-closable="false"
    >
      <n-spin :show="!!loadingAction">
        <template v-if="preview">
          <div class="mb-4 flex flex-wrap items-center gap-2">
            <n-tag size="small">
              v{{ preview.source_version }} → v{{ preview.target_version }}
            </n-tag>
            <n-tag
              size="small"
              :type="preview.status === 'completed' ? 'success' : 'warning'"
            >
              {{ preview.status }}
            </n-tag>
            <n-tag v-if="preview.not_collected.length" size="small" type="warning">
              {{ t("page.protocol.schemaGovernance.notCollectedCount", { count: preview.not_collected.length }) }}
            </n-tag>
          </div>

          <n-alert
            v-if="preview.not_collected.length"
            type="info"
            class="mb-4"
            :title="t('page.protocol.schemaGovernance.notCollectedTitle')"
          >
            <div class="text-sm">
              {{ preview.not_collected.join(", ") }}
            </div>
          </n-alert>

          <n-alert
            v-if="allIssues.length"
            :type="preview.schema_issues.length ? 'error' : 'warning'"
            class="mb-4"
            :title="t('page.protocol.schemaGovernance.issuesTitle')"
          >
            <ul class="list-disc space-y-1 pl-5 text-sm">
              <li v-for="(issue, index) in allIssues" :key="`${issue.path}-${index}`">
                <span v-if="issue.path" class="font-mono">{{ issue.path }}: </span>
                {{ issue.message }}
              </li>
            </ul>
          </n-alert>

          <n-collapse class="mb-4">
            <n-collapse-item :title="t('page.protocol.schemaGovernance.previewData')" name="data">
              <pre class="max-h-96 overflow-auto rounded-lg bg-gray-50 p-4 text-xs dark:bg-gray-900">{{ formattedPreview }}</pre>
            </n-collapse-item>
            <n-collapse-item
              v-if="preview.steps.length"
              :title="t('page.protocol.schemaGovernance.migrationPath')"
              name="steps"
            >
              <n-timeline>
                <n-timeline-item
                  v-for="step in preview.steps"
                  :key="`${step.from}-${step.to}`"
                  :type="step.status === 'completed' ? 'success' : 'warning'"
                  :title="`v${step.from} → v${step.to}`"
                  :content="step.status"
                />
              </n-timeline>
            </n-collapse-item>
          </n-collapse>

          <n-form-item
            v-if="mode === 'migration'"
            :label="t('page.protocol.schemaGovernance.reason')"
            required
          >
            <n-input
              v-model:value="reason"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 4 }"
              :placeholder="t('page.protocol.schemaGovernance.reasonPlaceholder')"
            />
          </n-form-item>
        </template>

        <template v-else-if="projection">
          <div class="mb-4 flex flex-wrap items-center gap-2">
            <n-tag size="small">
              v{{ projection.source_protocol_version }} → v{{ projection.target_protocol_version }}
            </n-tag>
            <n-tag :type="projection.status === 'completed' ? 'success' : 'warning'" size="small">
              {{ projection.status }}
            </n-tag>
            <n-tag v-if="projection.not_collected.length" type="warning" size="small">
              {{ t("page.protocol.schemaGovernance.notCollectedCount", { count: projection.not_collected.length }) }}
            </n-tag>
          </div>
          <n-alert
            v-if="projection.not_collected.length"
            type="info"
            class="mb-4"
            :title="t('page.protocol.schemaGovernance.notCollectedTitle')"
          >
            {{ projection.not_collected.join(", ") }}
          </n-alert>
          <pre class="max-h-[55vh] overflow-auto rounded-lg bg-gray-50 p-4 text-xs dark:bg-gray-900">{{ formattedProjection }}</pre>
        </template>
      </n-spin>

      <template #footer>
        <div class="flex justify-end gap-2">
          <n-button @click="showModal = false">
            {{ t("common.close") }}
          </n-button>
          <n-button
            v-if="mode === 'migration' && preview"
            type="primary"
            :loading="loadingAction === 'confirm'"
            :disabled="!canConfirmMigration"
            @click="confirmMigration"
          >
            {{ t("page.protocol.schemaGovernance.confirmMigration") }}
          </n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import type {
  GovernanceIssue,
  RecordMigrationPreview,
  RecordProjection,
} from "@/service/api/schema-governance"
import { getProtocolVersions } from "@/service/api/protocol"
import {
  migrateRecordSchema,
  previewRecordMigration,
  projectRecordSchema,
} from "@/service/api/schema-governance"
import { useClosableMessage } from "@airalogy/composables"
import IconTablerInfoCircle from "~icons/tabler/info-circle"
import { useI18n } from "vue-i18n"

const props = defineProps<{
  protocolId: string
  recordId: string
  sourceVersion: string
  allowMigration: boolean
}>()

const emit = defineEmits<{
  migrated: [record: { version: number, protocol_version: string }]
}>()

const { t } = useI18n()
const message = useClosableMessage()
const versions = ref<string[]>([])
const targetVersion = ref<string | null>(null)
const loadingVersions = ref(false)
const loadingAction = ref<"" | "projection" | "migration" | "confirm">("")
const mode = ref<"projection" | "migration">("projection")
const showModal = ref(false)
const preview = ref<RecordMigrationPreview | null>(null)
const projection = ref<RecordProjection | null>(null)
const reason = ref("")

const targetOptions = computed(() =>
  versions.value
    .filter(version => version !== props.sourceVersion)
    .map(version => ({ label: `v${version}`, value: version })),
)

const modalTitle = computed(() =>
  mode.value === "migration"
    ? t("page.protocol.schemaGovernance.migrationPreview")
    : t("page.protocol.schemaGovernance.projectionPreview"),
)

const allIssues = computed<GovernanceIssue[]>(() => [
  ...(preview.value?.issues || []),
  ...(preview.value?.schema_issues || []),
])

const formattedPreview = computed(() =>
  JSON.stringify(preview.value?.data || {}, null, 2),
)

const formattedProjection = computed(() =>
  JSON.stringify(projection.value?.projected_data || {}, null, 2),
)

const canConfirmMigration = computed(() =>
  Boolean(
    preview.value
    && reason.value.trim()
    && preview.value.schema_issues.length === 0
    && loadingAction.value !== "confirm",
  ),
)

async function loadVersions() {
  loadingVersions.value = true
  try {
    const { data, error } = await getProtocolVersions(props.protocolId, {
      page: 1,
      pageSize: 100,
    })
    if (error)
      throw error
    versions.value = (data?.versions || [])
      .map(version => String(version.version))
      .sort((left, right) => right.localeCompare(left, undefined, { numeric: true }))
    targetVersion.value = versions.value.find(version => version !== props.sourceVersion) || null
  }
  catch {
    versions.value = []
  }
  finally {
    loadingVersions.value = false
  }
}

async function openProjection() {
  if (!targetVersion.value)
    return
  mode.value = "projection"
  preview.value = null
  projection.value = null
  showModal.value = true
  loadingAction.value = "projection"
  try {
    projection.value = await projectRecordSchema(
      props.protocolId,
      props.recordId,
      targetVersion.value,
    )
  }
  catch {
    showModal.value = false
  }
  finally {
    loadingAction.value = ""
  }
}

async function openMigration() {
  if (!targetVersion.value)
    return
  mode.value = "migration"
  preview.value = null
  projection.value = null
  reason.value = ""
  showModal.value = true
  loadingAction.value = "migration"
  try {
    preview.value = await previewRecordMigration(
      props.protocolId,
      props.recordId,
      targetVersion.value,
    )
  }
  catch {
    showModal.value = false
  }
  finally {
    loadingAction.value = ""
  }
}

async function confirmMigration() {
  if (!targetVersion.value || !canConfirmMigration.value)
    return
  loadingAction.value = "confirm"
  try {
    const result = await migrateRecordSchema(props.protocolId, props.recordId, {
      target_version: targetVersion.value,
      reason: reason.value.trim(),
      idempotency_key: crypto.randomUUID(),
    })
    message.success(t("page.protocol.schemaGovernance.migrationSuccess"))
    showModal.value = false
    emit("migrated", result.record)
  }
  finally {
    loadingAction.value = ""
  }
}

watch(
  () => [props.protocolId, props.sourceVersion],
  () => void loadVersions(),
  { immediate: true },
)
</script>

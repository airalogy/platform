<template>
  <section v-if="hasResult" class="research-panel">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <div class="aira-type-eyebrow">
          {{ $t("page.research.resultPackage") }}
        </div>
        <h2 class="aira-type-section-title mb-0 mt-1">
          {{ $t("page.research.researchConclusion") }}
        </h2>
      </div>
      <div v-if="hasPackage" class="flex flex-wrap gap-2">
        <n-button size="small" secondary @click="openPackage">
          {{ $t("page.research.inspectResultPackage") }}
        </n-button>
        <n-dropdown :options="downloadOptions" @select="downloadPackage">
          <n-button size="small" secondary :loading="Boolean(downloading)">
            {{ $t("page.research.downloadResultPackage") }}
          </n-button>
        </n-dropdown>
      </div>
    </div>
    <p class="aira-type-body aira-text-secondary mb-0 mt-4 whitespace-pre-wrap">
      {{ conclusion || $t("page.research.noConclusion") }}
    </p>
    <div class="mt-4 flex flex-wrap gap-2">
      <n-tag v-if="outcome" type="success" round>
        {{ outcomeLabel(outcome) }}
      </n-tag>
      <n-tag v-if="scientificOutcome" type="info" round>
        {{ scientificOutcomeLabel(scientificOutcome) }}
      </n-tag>
    </div>
  </section>

  <n-modal
    v-model:show="visible"
    preset="card"
    class="research-result-package-modal"
    :title="$t('page.research.resultPackage')"
    :mask-closable="false"
  >
    <n-spin :show="loading">
      <n-alert v-if="loadError" type="error">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <span>{{ $t("page.research.resultPackageLoadError") }}</span>
          <n-button size="tiny" @click="loadPackage">
            {{ $t("common.retry") }}
          </n-button>
        </div>
      </n-alert>
      <template v-else-if="envelope">
        <n-alert :type="envelope.snapshot.sealed ? 'success' : 'warning'">
          {{ envelope.snapshot.sealed
            ? $t("page.research.resultPackageSealed")
            : $t("page.research.resultPackageUnsealed") }}
        </n-alert>

        <div class="research-result-meta mt-4">
          <div>
            <div class="aira-type-meta">
              {{ $t("page.research.resultPackageDigest") }}
            </div>
            <code class="aira-type-code mt-1 block break-all">{{ envelope.snapshot.digest }}</code>
          </div>
          <div>
            <div class="aira-type-meta">
              {{ $t("page.research.finalizedAt") }}
            </div>
            <div class="aira-type-label mt-1">
              {{ envelope.snapshot.finalized_at
                ? new Date(envelope.snapshot.finalized_at).toLocaleString()
                : $t("page.research.notFinalized") }}
            </div>
          </div>
        </div>

        <div class="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div v-for="metric in packageMetrics" :key="metric.label" class="research-result-metric">
            <div class="aira-type-meta">
              {{ metric.label }}
            </div>
            <div class="aira-type-section-title mt-1">
              {{ metric.value }}
            </div>
          </div>
        </div>

        <div class="mt-5 space-y-5">
          <div>
            <div class="aira-type-eyebrow">
              {{ $t("page.research.goal") }}
            </div>
            <p class="aira-type-body mb-0 mt-1 whitespace-pre-wrap">
              {{ envelope.package.goal || "-" }}
            </p>
          </div>
          <div>
            <div class="aira-type-eyebrow">
              {{ $t("page.research.successCriteria") }}
            </div>
            <ul class="aira-type-body mb-0 mt-2 pl-5 space-y-1">
              <li v-for="item in envelope.package.success_criteria || []" :key="item">
                {{ item }}
              </li>
            </ul>
          </div>
          <div>
            <div class="aira-type-eyebrow">
              {{ $t("page.research.reviewedConclusion") }}
            </div>
            <p class="aira-type-body mb-0 mt-1 whitespace-pre-wrap">
              {{ envelope.package.reviewed_conclusion
                || envelope.package.narrative_conclusion
                || $t("page.research.noConclusion") }}
            </p>
          </div>
          <n-collapse>
            <n-collapse-item :title="$t('page.research.completeResultSnapshot')" name="raw">
              <pre class="research-result-json">{{ resultPackageRaw }}</pre>
            </n-collapse-item>
          </n-collapse>
        </div>
      </template>
    </n-spin>

    <template #footer>
      <div class="flex flex-wrap justify-end gap-2">
        <n-button
          :loading="downloading === 'json'"
          :disabled="!envelope"
          @click="downloadPackage('json')"
        >
          JSON
        </n-button>
        <n-button
          :loading="downloading === 'markdown'"
          :disabled="!envelope"
          @click="downloadPackage('markdown')"
        >
          Markdown
        </n-button>
        <n-button type="primary" @click="visible = false">
          {{ $t("common.close") }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import type {
  ResearchResultPackage,
  ResearchResultPackageEnvelope,
} from "@/service/api/research-tasks"
import {
  downloadResearchResultPackage,
  fetchResearchResultPackage,
} from "@/service/api/research-tasks"
import { $t } from "@airalogy/shared/locales"
import { useMessage } from "naive-ui"
import { useI18n } from "vue-i18n"

const props = defineProps<{
  taskId: string
  outcome?: string | null
  scientificOutcome?: string | null
  conclusion?: string | null
  resultPackage: ResearchResultPackage | Record<string, never>
}>()

const { locale } = useI18n()
const message = useMessage()
const visible = ref(false)
const loading = ref(false)
const loadError = ref(false)
const downloading = ref<"json" | "markdown" | "">("")
const envelope = ref<ResearchResultPackageEnvelope | null>(null)

const hasPackage = computed(() => Object.keys(props.resultPackage || {}).length > 0)
const hasResult = computed(() => Boolean(props.conclusion || hasPackage.value))
const resultPackageRaw = computed(() => JSON.stringify(envelope.value, null, 2))
const packageMetrics = computed(() => {
  const result = envelope.value?.package
  return [
    { label: $t("page.research.claims"), value: result?.claims?.length || 0 },
    { label: $t("page.research.evidence"), value: result?.evidence?.length || 0 },
    { label: $t("page.research.dataAssets"), value: result?.data_assets?.length || 0 },
    { label: $t("page.research.actions"), value: result?.actions?.length || 0 },
  ]
})
const downloadOptions = computed(() => [
  { label: "JSON", key: "json" },
  { label: "Markdown", key: "markdown" },
])

function outcomeLabel(value: string) {
  return $t(`page.research.outcome.${value}` as I18n.I18nKey)
}

function scientificOutcomeLabel(value: string) {
  return $t(`page.research.scientificOutcomeValue.${value}` as I18n.I18nKey)
}

async function loadPackage() {
  loading.value = true
  loadError.value = false
  try {
    envelope.value = await fetchResearchResultPackage(props.taskId)
  }
  catch {
    envelope.value = null
    loadError.value = true
  }
  finally {
    loading.value = false
  }
}

function openPackage() {
  visible.value = true
  void loadPackage()
}

async function downloadPackage(selectedFormat: string | number) {
  const format = String(selectedFormat)
  if (format !== "json" && format !== "markdown")
    return
  downloading.value = format
  try {
    const language = locale.value.toLowerCase().startsWith("zh") ? "zh" : "en"
    const blob = await downloadResearchResultPackage(
      props.taskId,
      format,
      language,
    )
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement("a")
    anchor.href = url
    anchor.download = `research-task-${props.taskId}.${format === "json" ? "json" : "md"}`
    document.body.append(anchor)
    anchor.click()
    anchor.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 0)
  }
  catch {
    message.error($t("page.research.resultPackageDownloadError"))
  }
  finally {
    downloading.value = ""
  }
}

watch(() => props.taskId, () => {
  envelope.value = null
  loadError.value = false
})
</script>

<style scoped>
.research-result-package-modal {
  width: min(52rem, calc(100vw - 2rem));
}

.research-result-meta {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(0, 1fr);
  gap: 0.75rem;
}

.research-result-meta > div,
.research-result-metric {
  border: 1px solid rgb(226 232 240);
  border-radius: 0.75rem;
  background: rgb(248 250 252 / 75%);
  padding: 0.75rem;
}

.research-result-json {
  max-height: 24rem;
  overflow: auto;
  border-radius: 0.75rem;
  background: rgb(15 23 42);
  color: rgb(226 232 240);
  font-size: 0.75rem;
  line-height: 1.5;
  padding: 1rem;
  white-space: pre-wrap;
  word-break: break-word;
}

@media (max-width: 640px) {
  .research-result-meta {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>

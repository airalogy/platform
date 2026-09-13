<template>
  <section class="input-receipt my-4" data-testid="analysis-compute-input-receipt">
    <h4 class="aira-type-label">
      {{ t('page.analysis.compute.inputFilesReceipt') }}
    </h4>
    <p class="aira-type-body">
      {{ t('page.analysis.compute.inputFilesSummary', { count: envelope.count, bytes: envelope.total_bytes }) }}
    </p>
    <p class="aira-type-meta">
      {{ t('page.analysis.compute.inputFilesManifestHint', { filename: envelope.manifest.filename }) }}
    </p>
    <article v-for="file in envelope.files" :key="`${file.input_id}:${file.record_id}:${file.record_version}`" class="attachment-card mb-3" data-testid="analysis-compute-input-file">
      <strong>{{ file.filename }}</strong>
      <p class="aira-type-meta my-2">
        {{ file.media_type }} · {{ file.byte_size }} B · {{ file.input_id }}
      </p>
      <dl class="attachment-details aira-type-meta">
        <dt>{{ t('page.analysis.compute.inputFileSource') }}</dt>
        <dd>Record {{ file.record_id }} · v{{ file.record_version }}<br>{{ file.field_path.join(' · ') }} · Protocol {{ file.protocol_version }}</dd>
        <dt>{{ t('page.analysis.compute.inputFileMount') }}</dt>
        <dd>AIRALOGY_INPUT_DIR/{{ file.mount_name }}</dd>
        <dt>SHA-256</dt><dd>{{ file.checksum_sha256 }}</dd>
      </dl>
      <details class="mt-3">
        <summary>{{ t('page.analysis.compute.inputFileIntegrity') }}</summary>
        <dl class="attachment-details aira-type-meta mt-2">
          <dt>Record</dt><dd>{{ file.record_hash }}</dd>
          <dt>FileId</dt><dd>{{ file.file_id }}</dd>
          <dt>{{ t('page.workflowFiles.integrity') }}</dt><dd>{{ file.file_metadata_digest }}</dd>
        </dl>
      </details>
    </article>
    <details class="aira-type-meta">
      <summary>{{ envelope.manifest.filename }} · {{ envelope.manifest.byte_size }} B · SHA-256</summary>
      <p>{{ envelope.manifest.checksum_sha256 }}</p>
    </details>
  </section>
</template>

<script setup lang="ts">
import type { AnalysisComputeInputFilesEnvelope } from "@/service/api/analysis-compute"
import { useI18n } from "vue-i18n"

defineProps<{ envelope: AnalysisComputeInputFilesEnvelope }>()
const { t } = useI18n()
</script>

<style scoped>
.input-receipt { min-width: 0; overflow-wrap: anywhere; }
.attachment-card { padding: 12px; border: 1px solid #e2e8f0; border-radius: 8px; }
.attachment-details { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 6px 12px; margin: 0; }
.attachment-details dd { min-width: 0; margin: 0; overflow-wrap: anywhere; }
summary { cursor: pointer; }
summary:focus-visible { outline: 2px solid #0084e2; outline-offset: 2px; }
@media (max-width: 600px) { .attachment-details { grid-template-columns: minmax(0, 1fr); } }
</style>

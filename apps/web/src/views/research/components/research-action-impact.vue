<template>
  <div class="research-action-impact">
    <div class="flex flex-wrap items-center gap-2">
      <n-tag size="small" round :type="kindTagType">
        {{ kindLabel }}
      </n-tag>
      <span v-if="action.tool_job" class="aira-type-meta">
        {{ action.tool_job.tool_key }} · v{{ action.tool_job.tool_version }}
      </span>
      <span v-else-if="action.instrument_job" class="aira-type-meta">
        {{ action.instrument_job.command_key }} · v{{ action.instrument_job.command_version }} · r{{ action.instrument_job.command_revision }}
      </span>
      <span v-else-if="action.compute_job" class="aira-type-meta">
        {{ action.compute_job.environment_snapshot.name || action.compute_job.compute_environment_id }} · r{{ action.compute_job.compute_environment_revision }} · {{ action.compute_job.language === "python" ? "Python" : "R" }}
      </span>
      <span v-else-if="action.wait_event" class="aira-type-meta">
        {{ action.wait_event.expected_event_type }}
      </span>
      <span v-else-if="action.resource_reservation" class="aira-type-meta">
        {{ resolvedResource.resource_name || action.resource_reservation.resource_id }}
        <template v-if="resolvedResource.resource_code">
          · {{ resolvedResource.resource_code }}
        </template>
      </span>
      <span v-else-if="action.service_job" class="aira-type-meta">
        {{ action.service_job.provider_snapshot.name }} · {{ action.service_job.offering_snapshot.name }} · v{{ action.service_job.service_version }}
      </span>
      <span v-else-if="action.protocol" class="aira-type-meta">
        {{ action.protocol.name }} · v{{ action.protocol.version }}
      </span>
    </div>

    <div v-if="action.tool_job" class="mt-2">
      <div class="aira-type-meta">{{ $t("page.research.toolArguments") }}</div>
      <pre>{{ formatted(action.tool_job.arguments) }}</pre>
    </div>
    <div v-else-if="action.instrument_job" class="mt-2 space-y-2">
      <div class="flex flex-wrap gap-x-4 gap-y-1 aira-type-meta">
        <span>{{ $t("page.research.equipment") }} · {{ instrumentResource }}</span>
        <span>{{ $t("page.research.gateway") }} · {{ action.input_data.gateway_name || action.instrument_job.gateway_id }}</span>
        <span>{{ $t("page.research.approvedBooking") }} · {{ action.instrument_job.equipment_booking_id }}</span>
        <span>{{ $t(`page.resourceLibrary.risk.${action.instrument_job.risk}` as I18n.I18nKey) }}</span>
        <span>
          {{ formatDate(bookingWindow.starts_at) }} – {{ formatDate(bookingWindow.ends_at) }}
        </span>
      </div>
      <div class="aira-type-meta">
        {{ $t("page.research.deviceConfirmation") }} ·
        {{ action.instrument_job.device_confirmation_required ? $t("page.research.deviceConfirmationRequired") : $t("page.research.deviceConfirmationNotRequired") }}
      </div>
      <div>
        <div class="aira-type-meta">{{ $t("page.research.instrumentArguments") }}</div>
        <pre>{{ formatted(action.instrument_job.arguments) }}</pre>
      </div>
    </div>
    <div v-else-if="action.compute_job" class="mt-2 space-y-2">
      <div class="flex flex-wrap gap-x-4 gap-y-1 aira-type-meta">
        <span>{{ $t("page.research.computeEnvironment") }} · {{ action.compute_job.environment_snapshot.name || action.compute_job.compute_environment_id }} · r{{ action.compute_job.compute_environment_revision }}</span>
        <span>{{ $t("page.research.computeSourceDigest") }} · {{ action.compute_job.source_sha256 }}</span>
        <span v-if="action.compute_job.estimated_cost">≤ {{ action.compute_job.estimated_cost }} {{ action.compute_job.currency }}</span>
      </div>
      <div>
        <div class="aira-type-meta">{{ $t("page.research.computeResourceLimits") }}</div>
        <pre>{{ formatted(action.compute_job.resource_limits) }}</pre>
      </div>
      <div>
        <div class="aira-type-meta">{{ $t("page.research.computeInputPayload") }}</div>
        <pre>{{ formatted(action.compute_job.input_payload) }}</pre>
      </div>
    </div>
    <div v-else-if="action.wait_event" class="mt-2">
      <div class="aira-type-meta">{{ $t("page.research.expectedPayload") }}</div>
      <pre>{{ formatted(action.wait_event.payload_schema) }}</pre>
    </div>
    <div v-else-if="action.resource_reservation" class="mt-2">
      <div class="aira-type-meta">{{ $t("page.research.reservationImpact") }}</div>
      <div class="aira-type-body mt-1">
        <template v-if="action.resource_reservation.kind === 'inventory'">
          {{ action.resource_reservation.quantity }} {{ action.resource_reservation.unit }}
        </template>
        <template v-else>
          {{ formatDate(action.resource_reservation.starts_at) }} – {{ formatDate(action.resource_reservation.ends_at) }}
        </template>
      </div>
      <p class="aira-type-meta aira-text-muted mb-0 mt-1">
        {{ action.resource_reservation.purpose }}
      </p>
    </div>
    <div v-else-if="action.service_job" class="mt-2 space-y-2">
      <div class="flex flex-wrap gap-x-4 gap-y-1 aira-type-meta">
        <span>{{ $t("page.research.serviceJobStatusLabel") }} · {{ $t(`page.research.serviceJobStatus.${action.service_job.status}` as I18n.I18nKey) }}</span>
        <span>{{ $t("page.research.serviceContractRevision") }} · r{{ action.service_job.service_offering_revision }}</span>
        <span v-if="action.service_job.quote">{{ action.service_job.quote.amount }} {{ action.service_job.quote.currency }}</span>
      </div>
      <div>
        <div class="aira-type-meta">{{ $t("page.research.serviceRequestPayload") }}</div>
        <pre>{{ formatted(action.service_job.request_payload) }}</pre>
      </div>
    </div>
    <div v-else-if="action.protocol_run && Object.keys(action.protocol_run.initial_values || {}).length" class="mt-2">
      <div class="aira-type-meta">{{ $t("page.research.initialValues") }}</div>
      <pre>{{ formatted(action.protocol_run.initial_values) }}</pre>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { ResearchAction } from "@/service/api/research-tasks"
import type { TagProps } from "naive-ui"
import { $t } from "@airalogy/shared/locales"

const props = defineProps<{ action: ResearchAction }>()

const kindLabel = computed(() => {
  const known = ["protocol_run", "tool_job", "instrument_job", "compute_job", "external_service_job", "resource_reservation", "wait_event", "human_work_item"]
  return known.includes(props.action.kind)
    ? $t(`page.research.actionKind.${props.action.kind}` as I18n.I18nKey)
    : props.action.kind.replaceAll("_", " ")
})

const kindTagType = computed<TagProps["type"]>(() => {
  if (props.action.kind === "tool_job")
    return "info"
  if (props.action.kind === "wait_event")
    return "warning"
  if (props.action.kind === "instrument_job")
    return "warning"
  if (props.action.kind === "compute_job")
    return "warning"
  if (props.action.kind === "resource_reservation")
    return "warning"
  if (props.action.kind === "external_service_job")
    return "warning"
  return "default"
})

const resolvedResource = computed(() => (
  (props.action.input_data?.resolved || {}) as Record<string, string>
))

const bookingWindow = computed(() => (
  (props.action.requirements?.booking_window || {}) as Record<string, string>
))

const instrumentResource = computed(() => {
  const name = String(props.action.input_data?.resource_name || props.action.instrument_job?.resource_id || "")
  const code = String(props.action.input_data?.resource_code || "")
  return code ? `${name} · ${code}` : name
})

function formatDate(value?: string | null) {
  return value ? new Date(value).toLocaleString() : "—"
}

function formatted(value: Record<string, unknown>) {
  return JSON.stringify(value || {}, null, 2)
}
</script>

<style scoped>
.research-action-impact {
  margin-top: 0.75rem;
  border: 1px solid rgb(226 232 240);
  border-radius: 0.75rem;
  background: rgb(248 250 252 / 80%);
  padding: 0.75rem;
}

pre {
  max-height: 12rem;
  overflow: auto;
  margin: 0.35rem 0 0;
  border-radius: 0.5rem;
  background: rgb(255 255 255 / 85%);
  padding: 0.625rem;
  color: rgb(51 65 85);
  font-size: 0.75rem;
  line-height: 1.5;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
</style>

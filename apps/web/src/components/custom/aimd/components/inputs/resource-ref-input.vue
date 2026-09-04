<template>
  <AimdResourceRefField
    v-if="resourceConfig"
    :node="node"
    :value="props.model.value"
    :disabled="props.disabled"
    :messages="messages"
    :field-meta="fieldMeta"
    :type="resourceType"
    :resource-config="resourceConfig"
    :resource-resolvers="resolvers"
    :record="record"
    @change="handleChange($event.value)"
    @blur="handleBlur"
  />
  <label
    v-if="showReservationSelector"
    class="platform-resource-reservation"
  >
    <span>{{ t("page.protocol.addRecord.resourceReservation") }}</span>
    <select
      data-testid="resource-reservation-select"
      :disabled="props.disabled"
      :value="selectedResourceValue?.reservation_id || ''"
      @change="handleReservationChange(($event.target as HTMLSelectElement).value)"
      @blur="handleBlur"
    >
      <option value="">
        {{ t("page.protocol.addRecord.noResourceReservation") }}
      </option>
      <option
        v-for="reservation in reservationOptions"
        :key="reservation.id"
        :value="reservation.id"
        :disabled="reservation.unavailable"
      >
        {{ reservation.label }}
      </option>
    </select>
    <small>{{ t("page.protocol.addRecord.resourceReservationHint") }}</small>
  </label>
</template>

<script setup lang="ts">
import type { ResearchInventoryReservationOption } from "@/service/api/resources"
import type { AimdVarNode } from "@airalogy/aimd-core/types"
import type { AimdFieldMeta } from "@airalogy/aimd-recorder"
import type { IAIMDInputProps } from "../../types/props"
import {
  AimdResourceRefField,
  createAimdRecorderMessages,
  createEmptyProtocolRecordData,
  getResourceRefTypeConfig,
} from "@airalogy/aimd-recorder"
import { useI18n } from "vue-i18n"
import { useAIMDInject } from "../../composables/useAIMDHelpers"
import { platformResourceResolverKey } from "../../resourceResolver"

const props = defineProps<IAIMDInputProps>()
const resourceContext = inject(platformResourceResolverKey, null)
const aimdContext = useAIMDInject()
const { locale, t } = useI18n()
const emptyRecord = createEmptyProtocolRecordData()
const resolvers = computed(() => resourceContext?.resolvers.value)
const record = computed(() => resourceContext?.record.value || emptyRecord)

const resourceType = computed(() =>
  String(props.info?.type_annotation || props.info?.type || props.type),
)

const kwargs = computed<Record<string, unknown>>(() => {
  const value = props.info?.kwargs || props.info?.definition?.kwargs
  return value && typeof value === "object" ? value : {}
})

const schema = computed<Record<string, unknown>>(() => {
  const value = props.ajvInfo?.schema
  return value && typeof value === "object" ? value : {}
})

const fieldMeta = computed<AimdFieldMeta>(() => ({
  title: typeof schema.value.title === "string" ? schema.value.title : props.placeholder,
  description: typeof schema.value.description === "string" ? schema.value.description : undefined,
  examples: Array.isArray(schema.value.examples) ? schema.value.examples : undefined,
  required: props.required === true,
  entity: typeof schema.value.entity === "string" ? schema.value.entity : undefined,
  source: typeof schema.value.source === "string" ? schema.value.source : undefined,
  resource_role: (schema.value.resource_role || kwargs.value.resource_role) as AimdFieldMeta["resource_role"],
  quantity_field: String(schema.value.quantity_field || kwargs.value.quantity_field || "") || undefined,
  container_required: schema.value.container_required === true || kwargs.value.container_required === true,
  booking_required: schema.value.booking_required === true || kwargs.value.booking_required === true,
}))

const resourceConfig = computed(() =>
  getResourceRefTypeConfig(resourceType.value, kwargs.value, fieldMeta.value),
)

const selectedResourceValue = computed<Record<string, any> | null>(() => {
  const value = props.model.value
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, any>
    : null
})

const showReservationSelector = computed(() =>
  resourceConfig.value?.role === "input"
  && resourceConfig.value.multiple !== true
  && Boolean(selectedResourceValue.value?.id),
)

const reservationOptions = computed<Array<ResearchInventoryReservationOption & {
  unavailable?: boolean
}>>(() => {
  const resourceId = String(selectedResourceValue.value?.id || "")
  const options = resourceContext?.inventoryReservations.value[resourceId] || []
  const selectedId = String(selectedResourceValue.value?.reservation_id || "")
  if (!selectedId || options.some(item => item.id === selectedId))
    return options
  return [
    {
      id: selectedId,
      research_reservation_id: "",
      container_id: String(selectedResourceValue.value?.container_id || ""),
      quantity: "",
      unit: String(selectedResourceValue.value?.unit || ""),
      task_id: "",
      task_title: "",
      action_title: "",
      label: t("page.protocol.addRecord.unavailableResourceReservation", {
        id: selectedId,
      }),
      unavailable: true,
    },
    ...options,
  ]
})

const node = computed<AimdVarNode>(() => ({
  type: "aimd",
  fieldType: "var",
  scope: "var",
  id: props.prop,
  raw: String(props.info?.raw || `{{var|${props.prop}}}`),
  definition: {
    id: props.prop,
    type: resourceType.value,
    kwargs: kwargs.value,
  },
}))

const messages = computed(() =>
  createAimdRecorderMessages(locale.value.toLowerCase().startsWith("zh") ? "zh-CN" : "en-US"),
)

function handleChange(value: unknown) {
  let nextValue = value
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const next = value as Record<string, any>
    const reservation = reservationOptions.value.find(
      item => item.id === next.reservation_id && !item.unavailable,
    )
    if (reservation && next.container_id !== reservation.container_id) {
      const normalized = { ...next }
      delete normalized.reservation_id
      if (normalized.snapshot && typeof normalized.snapshot === "object") {
        normalized.snapshot = { ...normalized.snapshot }
        delete normalized.snapshot.research_reservation
      }
      nextValue = normalized
    }
  }
  aimdContext?.handleFieldChange({
    scope: props.scope,
    prop: props.prop,
    value: nextValue,
    assigner: props.assigner,
    dependent: props.dependent,
    info: props.info,
  })
}

function handleReservationChange(reservationId: string) {
  const current = selectedResourceValue.value
  if (!current)
    return
  const reservation = reservationOptions.value.find(item => item.id === reservationId)
  const next = { ...current }
  if (!reservationId) {
    delete next.reservation_id
    if (next.snapshot && typeof next.snapshot === "object") {
      next.snapshot = { ...next.snapshot }
      delete next.snapshot.research_reservation
    }
  }
  else if (reservation && !reservation.unavailable) {
    next.reservation_id = reservation.id
    next.container_id = reservation.container_id
    next.unit ||= reservation.unit
    next.snapshot = {
      ...(next.snapshot && typeof next.snapshot === "object" ? next.snapshot : {}),
      research_reservation: {
        id: reservation.id,
        research_reservation_id: reservation.research_reservation_id,
        task_id: reservation.task_id,
        task_title: reservation.task_title,
        label: reservation.label,
        quantity: reservation.quantity,
        unit: reservation.unit,
      },
    }
  }
  handleChange(next)
}

function handleBlur() {
  const currentTarget = document.getElementById(props.id) || document.body
  aimdContext?.handleInputBlur({ currentTarget } as unknown as FocusEvent, props.scope, props.prop)
}
</script>

<style scoped>
.platform-resource-reservation {
  display: grid;
  min-width: 0;
  grid-template-columns: minmax(5rem, max-content) minmax(0, 1fr);
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.5rem;
  color: var(--aimd-rec-text-muted, #64748b);
  font-size: 0.8125rem;
}

.platform-resource-reservation select {
  min-width: 0;
  height: 2rem;
  border: 1px solid var(--aimd-rec-border, #cbd5e1);
  border-radius: 0.375rem;
  background: var(--aimd-rec-surface, #fff);
  color: var(--aimd-rec-text, #0f172a);
  padding: 0 0.5rem;
}

.platform-resource-reservation small {
  grid-column: 2;
  line-height: 1.35;
}

@media (max-width: 640px) {
  .platform-resource-reservation {
    grid-template-columns: 1fr;
  }

  .platform-resource-reservation small {
    grid-column: 1;
  }
}
</style>

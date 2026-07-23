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
</template>

<script setup lang="ts">
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
const { locale } = useI18n()
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
  aimdContext?.handleFieldChange({
    scope: props.scope,
    prop: props.prop,
    value,
    assigner: props.assigner,
    dependent: props.dependent,
    info: props.info,
  })
}

function handleBlur() {
  const currentTarget = document.getElementById(props.id) || document.body
  aimdContext?.handleInputBlur({ currentTarget } as unknown as FocusEvent, props.scope, props.prop)
}
</script>

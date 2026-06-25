<template>
  <list-protocol-item
    v-if="props.type === 'protocol'"
    :item="(props.item as ProtocolModels.ProjectProtocolInfo)"
    class="group relative"
    v-bind="$attrs"
  />
  <list-lab-item
    v-if="props.type === 'lab'"
    :item="(props.item as Api.Lab.LabInfo)"
    class="group relative"
    v-bind="$attrs"
  />
  <list-project-item
    v-if="props.type === 'project'"
    :item="(props.item as Api.Project.MyProjectInfo)"
    class="group relative"
    v-bind="$attrs"
  />
</template>

<script setup lang="ts">
import type { ProtocolModels } from "@airalogy/shared/types"

export interface IProps {
  type: "lab" | "project" | "protocol"
  item: Api.Lab.LabInfo | Api.Project.MyProjectInfo | ProtocolModels.ProjectProtocolInfo
  isCompact?: boolean
}

defineOptions({ name: "SiderItem", inheritAttrs: false })

const props = withDefaults(defineProps<IProps>(), {
  isCompact: true,
})
</script>

<style scoped></style>

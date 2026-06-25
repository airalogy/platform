<template>
  <n-list hoverable clickable>
    <template v-for="item in props.list" :key="item.name">
      <n-list-item v-if="props.showPrivate || item.type !== 1">
        <template #prefix>
          <group-icon class="align-middle" />
        </template>
        <lab-group-item :item="item" :is-compact="false" class="w-fit" />
        <template #suffix>
          <div v-if="props.showActions" class="flex">
            <edit-button :item="item" type="group" />
          </div>
        </template>
      </n-list-item>
    </template>
  </n-list>
</template>

<script setup lang="ts">
import LabGroupItem from "./lab-group-item.vue"

defineOptions({ name: "LabProjectList" })

const props = withDefaults(
  defineProps<IProps>(),
  {
    list: () => [],
    showActions: false,
    showPrivate: true,
  },
)

interface IProps {
  list: Api.Groups.MyGroupsInfo[]
  showPrivate?: boolean
  showActions?: boolean
}
</script>

<style scoped></style>

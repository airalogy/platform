<template>
  <n-list hoverable clickable>
    <template v-for="item in props.list" :key="item.id">
      <n-list-item v-if="props.showPrivate || item.type !== 1" class="group">
        <template #prefix>
          <n-avatar
            v-if="Boolean(item.logo_url)"
            class="align-middle"
            :src="item.logo_url!"
            :size="40"
            object-fit="cover"
            color="transparent"
          />
          <lab-icon v-else class="align-middle" />
        </template>
        <list-lab-item :item="item" :is-compact="false" class="min-w-0 flex-1" />
        <template v-if="showPin || (props.showActions && checkPermission(item))" #suffix>
          <div class="flex items-center gap-2">
            <edit-button v-if="props.showActions && checkPermission(item)" :item="item" type="lab" />
            <n-tooltip v-if="showPin" placement="top">
              <template #trigger>
                <n-button
                  quaternary
                  size="small"
                  class="pin-action"
                  :class="{ 'pin-action--active': isPinning(item) }"
                  :loading="isPinning(item)"
                  @click.stop="handleTogglePin(item, $event)"
                >
                  <n-icon
                    :component="PinnedIcon"
                    :size="16"
                    :color="isPinned(item) ? '#0084E2' : '#A1A4AF'"
                  />
                </n-button>
              </template>
              {{ isPinned(item) ? $t("icon.unpin") : $t("icon.pin") }}
            </n-tooltip>
          </div>
        </template>
      </n-list-item>
    </template>
  </n-list>
</template>

<script setup lang="ts">
import { checkLabActionPermission, LabAction } from "@/composables/useLabPermissions"
import { type PinnedItem, PinnedResourceType } from "@/service/api/pinned-items"
import { $t } from "@airalogy/shared/locales"
import PinnedIcon from "~icons/tabler/pinned"

defineOptions({ name: "LabList" })

const props = withDefaults(defineProps<IProps>(), {
  list: () => [],
  showPrivate: true,
  showActions: true,
})

const emits = defineEmits<{
  (ev: "togglePin", payload: { resourceType: PinnedResourceType, resourceId: string }): void
}>()

interface IProps {
  list: (Api.Lab.LabInfo | Api.Lab.UsersLabInfo)[]
  showActions?: boolean
  showPrivate?: boolean
  pinnedMap?: Map<string, PinnedItem>
  pinningKeys?: Set<string>
}

const showPin = computed(() => Boolean(props.pinnedMap))

function getPinnedKey(item: IProps["list"][number]) {
  const id = (item as { id?: string }).id
  return id ? `${PinnedResourceType.Lab}:${id}` : null
}

function isPinned(item: IProps["list"][number]) {
  const key = getPinnedKey(item)
  if (!key || !props.pinnedMap) {
    return false
  }
  return props.pinnedMap.has(key)
}

function isPinning(item: IProps["list"][number]) {
  const key = getPinnedKey(item)
  if (!key || !props.pinningKeys) {
    return false
  }
  return props.pinningKeys.has(key)
}

function handleTogglePin(item: IProps["list"][number], event: MouseEvent) {
  event.preventDefault()
  event.stopPropagation()
  const id = (item as { id?: string }).id
  if (!id) {
    return
  }
  emits("togglePin", { resourceType: PinnedResourceType.Lab, resourceId: id })
}

function checkPermission(item: IProps["list"][number]) {
  const role = (item as Api.Lab.UsersLabInfo)?.user_role
  if (!role) {
    return false
  }

  return checkLabActionPermission(role, LabAction.MANAGE_LAB)
}
</script>

<style scoped lang="sass">
.pin-action
  opacity: 1
  transition: opacity .2s ease

.pin-action--active
  opacity: 1
</style>

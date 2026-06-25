<template>
  <n-modal
    :show="show"
    :mask-closable="false"
    preset="dialog"
    :title="$t('common.deleteEntityTitle', { entity: entityName })"
    :show-icon="false"
    :positive-text="$t('common.delete')"
    :negative-text="$t('common.cancel')"
    :positive-button-props="{
      type: 'error',
      disabled: !isDeleteConfirmationValid,
      loading: deleting,
    }"
    :negative-button-props="{ disabled: deleting }"
    @positive-click="$emit('confirm')"
    @negative-click="$emit('cancel')"
    @close="$emit('cancel')"
  >
    <div class="space-y-4">
      <div class="flex items-center border border-red-200 rounded-lg bg-red-50 p-4 space-x-3">
        <n-icon class="text-red-500">
          <icon-tabler-alert-triangle />
        </n-icon>
        <div class="flex-1">
          <h3 class="text-sm text-red-800 font-medium">
            {{ $t("common.deleteWarningTitle") }}
          </h3>
          <p class="mt-1 text-sm text-red-700">
            {{ $t("common.deleteWarningBody", { entity: entityName }) }}
          </p>
        </div>
      </div>

      <div
        v-if="extraWarning"
        class="flex items-start border border-amber-200 rounded-lg bg-amber-50 p-3 text-amber-800 text-xs"
      >
        <n-icon class="mt-0.5 text-amber-500">
          <icon-tabler-info-circle />
        </n-icon>
        <p class="ml-2">
          {{ extraWarning }}
        </p>
      </div>

      <div class="space-y-3">
        <p class="text-sm text-gray-900 dark:text-gray-100">
          {{ $t("common.deleteAboutTo", { entity: entityName }) }}
        </p>
        <div class="rounded-lg bg-gray-100 p-3 dark:bg-gray-800">
          <p class="text-gray-900 font-medium dark:text-gray-100">
            {{ itemName }}
          </p>
        </div>

        <div class="space-y-2">
          <label class="block text-sm text-gray-700 font-medium dark:text-gray-300">
            {{ $t("common.typeToConfirm", { keyword: "DELETE" }) }}
          </label>
          <n-input
            :value="deleteConfirmationText"
            :placeholder="$t('common.typeToConfirmPlaceholder', { keyword: 'DELETE' })"
            :disabled="deleting"
            class="!rounded-lg"
            @update:value="$emit('update:deleteConfirmationText', $event)"
            @keyup.enter="isDeleteConfirmationValid && $emit('confirm')"
          />
        </div>
      </div>
    </div>
  </n-modal>
</template>

<script setup lang="ts">
interface Props {
  show: boolean
  entityName: string
  itemName: string
  deleteConfirmationText: string
  isDeleteConfirmationValid: boolean
  deleting: boolean
  extraWarning?: string
}

defineProps<Props>()

defineEmits<Emits>()

interface Emits {
  (e: "update:deleteConfirmationText", value: string): void
  (e: "confirm"): void
  (e: "cancel"): void
}
</script>

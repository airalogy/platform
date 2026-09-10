<script setup lang="ts">
import type { AdapterMatchResult, AdapterProfileField, AdapterTargetProfile } from "@/service/api/instrument-packages"
import { adapterProfileFields, matchAdapterPackages } from "@/service/api/instrument-packages"
import { $t } from "@airalogy/shared/locales"

const props = defineProps<{ labId: string, disabled: boolean }>()
const emit = defineEmits<{ inspect: [id: string], import: [] }>()
const show = ref(false)
const busy = ref(false)
const includeRevoked = ref(false)
const result = ref<AdapterMatchResult | null>(null)
const profile = reactive<Record<AdapterProfileField, string>>({ manufacturer: "", model: "", firmware: "", application: "", application_version: "", os: "", architecture: "", gateway_version: "", python_version: "" })
let epoch = 0

watch([profile, includeRevoked, () => props.labId], () => {
  epoch += 1
  result.value = null
}, { deep: true, flush: "sync" })
watch(show, () => {
  epoch += 1
  result.value = null
})

async function search(more = false) {
  if (busy.value || props.disabled || !profile.manufacturer.trim() || !profile.model.trim())
    return
  busy.value = true
  const requestEpoch = ++epoch
  const snapshot = Object.fromEntries(adapterProfileFields.map(field => [field, profile[field].trim() || null])) as AdapterTargetProfile
  try {
    const next = await matchAdapterPackages(props.labId, snapshot, includeRevoked.value, more ? result.value?.next_offset ?? 0 : 0)
    if (requestEpoch !== epoch)
      return
    result.value = more && result.value
      ? { ...next, items: [...new Map([...result.value.items, ...next.items].map(item => [item.release.id, item])).values()] }
      : next
  }
  catch {
    if (requestEpoch === epoch) {
      result.value = null
      window.$message?.error($t("page.resourceLibrary.adapterMatchRetry"))
    }
  }
  finally { busy.value = false }
}
function inspect(id: string) {
  show.value = false
  emit("inspect", id)
}
function importPackage() {
  show.value = false
  emit("import")
}
</script>

<template>
  <n-button :disabled="disabled" @click="show = true">
    {{ $t("page.resourceLibrary.adapterMatchTitle") }}
  </n-button>
  <n-modal v-model:show="show" preset="card" class="aira-dialog" :title="$t('page.resourceLibrary.adapterMatchTitle')" :mask-closable="false" style="--aira-dialog-width: 52rem">
    <p class="mb-3">
      {{ $t("page.resourceLibrary.adapterMatchHint") }}
    </p>
    <n-form label-placement="top" @submit.prevent="search()">
      <div class="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
        <n-form-item v-for="field in adapterProfileFields.slice(0, 2)" :key="field" :label="$t(`page.resourceLibrary.adapterMatchFields.${field}`)" required>
          <n-input v-model:value="profile[field]" :disabled="busy" :maxlength="256" :data-testid="`adapter-match-${field}`" :aria-label="$t(`page.resourceLibrary.adapterMatchFields.${field}`)" />
        </n-form-item>
      </div>
      <n-collapse class="mb-4">
        <n-collapse-item name="details" :title="$t('page.resourceLibrary.adapterMatchDetails')">
          <div class="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
            <n-form-item v-for="field in adapterProfileFields.slice(2)" :key="field" :label="$t(`page.resourceLibrary.adapterMatchFields.${field}`)">
              <n-input v-model:value="profile[field]" :disabled="busy" :maxlength="256" :data-testid="`adapter-match-${field}`" :placeholder="$t('page.resourceLibrary.adapterMatchUnknown')" :aria-label="$t(`page.resourceLibrary.adapterMatchFields.${field}`)" />
            </n-form-item>
          </div>
        </n-collapse-item>
      </n-collapse>
      <n-space align="center" class="mb-4">
        <n-button attr-type="submit" type="primary" :loading="busy" :disabled="disabled || !profile.manufacturer.trim() || !profile.model.trim()" data-testid="adapter-match-search">
          {{ $t("page.resourceLibrary.adapterMatchSearch") }}
        </n-button>
        <n-checkbox v-model:checked="includeRevoked" :disabled="busy">
          {{ $t("page.resourceLibrary.adapterMatchIncludeRevoked") }}
        </n-checkbox>
      </n-space>
    </n-form>
    <n-alert type="warning" class="mb-4">
      {{ $t("page.resourceLibrary.adapterMatchAuthority") }}
    </n-alert>
    <div v-if="result" aria-live="polite" data-testid="adapter-match-results">
      <n-empty v-if="!result.items.length" :description="$t('page.resourceLibrary.adapterMatchEmpty')" class="my-4" />
      <article v-for="candidate in result.items" :key="candidate.release.id" class="mb-3 min-w-0 border border-gray-200 rounded-lg p-3" data-testid="adapter-match-candidate">
        <h4 class="break-all">
          {{ candidate.release.package_key }} · {{ candidate.release.package_version }}
        </h4>
        <n-space class="my-2">
          <n-tag :type="candidate.comparison.status === 'conflicts' ? 'error' : 'info'" size="small">
            {{ $t(`page.resourceLibrary.adapterMatchStatus.${candidate.comparison.status}`) }}
          </n-tag>
          <n-tag :type="candidate.release.state === 'revoked' ? 'error' : 'default'" size="small">
            {{ $t(`page.resourceLibrary.adapterState.${candidate.release.state}`) }}
          </n-tag>
        </n-space>
        <code class="mb-2 block break-all text-xs">SHA-256: {{ candidate.release.archive_digest }}</code>
        <n-collapse>
          <n-collapse-item v-for="combination in candidate.comparison.combinations" :key="combination.combination_index" :name="combination.combination_index" :title="$t('page.resourceLibrary.adapterMatchCombination', { index: combination.combination_index + 1, status: $t(`page.resourceLibrary.adapterMatchStatus.${combination.status}`) })">
            <dl class="space-y-3">
              <div v-for="check in combination.checks" :key="check.field" class="min-w-0">
                <dt class="font-medium">
                  {{ $t(`page.resourceLibrary.adapterMatchFields.${check.field}`) }} · {{ $t(`page.resourceLibrary.adapterMatchCheck.${check.status}`) }}
                </dt>
                <dd class="m-0 break-words">
                  {{ $t("page.resourceLibrary.adapterMatchSupplied") }}: {{ check.supplied ?? $t("page.resourceLibrary.adapterMatchUnknown") }}<br>
                  {{ $t("page.resourceLibrary.adapterMatchDeclared") }}: {{ check.declared.join(" · ") }}
                </dd>
              </div>
            </dl>
            <p class="mt-3">
              {{ $t("page.resourceLibrary.adapterMatchTestClaims") }}
            </p>
            <p v-if="!combination.test_declarations.length">
              {{ $t("page.resourceLibrary.adapterMatchNoTests") }}
            </p>
            <p v-for="(claim, index) in combination.test_declarations" :key="index" class="mt-2 break-words">
              {{ claim.reference }} · {{ claim.simulation_only ? $t("page.resourceLibrary.adapterMatchSimulation") : $t("page.resourceLibrary.adapterMatchUnverifiedClaim") }}
            </p>
          </n-collapse-item>
        </n-collapse>
        <n-button class="mt-3" :disabled="busy || disabled" @click="inspect(candidate.release.id)">
          {{ $t("page.resourceLibrary.adapterInspect") }}
        </n-button>
      </article>
      <n-button v-if="result.has_more" :loading="busy" @click="search(true)">
        {{ $t("page.resourceLibrary.adapterMore") }}
      </n-button>
    </div>
    <template #footer>
      <n-space justify="end">
        <n-button :disabled="busy" @click="show = false">
          {{ $t("common.close") }}
        </n-button>
        <n-button :disabled="busy || disabled" @click="importPackage">
          {{ $t("page.resourceLibrary.adapterImport") }}
        </n-button>
      </n-space>
    </template>
  </n-modal>
</template>

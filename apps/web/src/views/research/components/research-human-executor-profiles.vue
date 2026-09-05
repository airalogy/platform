<template>
  <n-button secondary @click="open">
    <template #icon><n-icon><icon-tabler-users /></n-icon></template>
    {{ $t("page.research.humanExecutorProfiles") }}
  </n-button>

  <n-modal
    style="--aira-dialog-width: 58rem"
    v-model:show="visible"
    preset="card"
    class="aira-dialog human-executor-modal"
    :title="$t('page.research.humanExecutorProfiles')"
    :mask-closable="false"
    @after-leave="resetEditor"
  >
    <n-alert type="info" class="mb-4">
      {{ $t("page.research.humanExecutorProfilesHint") }}
    </n-alert>

    <n-spin :show="loading">
      <template v-if="!editing">
        <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div class="aira-type-meta">
            {{ $t("page.research.humanExecutorProfileCount", { count: profiles.length }) }}
          </div>
          <n-button
            type="primary"
            :disabled="availableMemberOptions.length === 0"
            @click="beginCreate"
          >
            {{ $t("page.research.addHumanExecutorProfile") }}
          </n-button>
        </div>

        <div v-if="profiles.length" class="space-y-3">
          <article v-for="profile in profiles" :key="profile.id" class="human-executor-card">
            <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div class="min-w-0">
                <div class="flex flex-wrap items-center gap-2">
                  <strong class="aira-type-label">{{ userLabel(profile.user) }}</strong>
                  <n-tag
                    :type="profile.currently_available ? 'success' : 'default'"
                    size="small"
                    round
                  >
                    {{ profile.currently_available
                      ? $t("page.research.executorAvailable")
                      : (profile.availability === "unavailable"
                        ? $t("page.research.executorUnavailable")
                        : $t("page.research.executorOutsideWindow")) }}
                  </n-tag>
                  <n-tag size="small" round>
                    {{ $t("page.research.humanExecutorCapacity", {
                      active: profile.active_workload,
                      capacity: profile.max_concurrent_items,
                    }) }}
                  </n-tag>
                </div>
                <div v-if="profile.skills.length" class="mt-3 flex flex-wrap gap-2">
                  <n-tag
                    v-for="skill in profile.skills"
                    :key="skill.key"
                    :type="skill.verified ? 'info' : 'warning'"
                    size="small"
                    round
                  >
                    {{ skill.name }} · L{{ skill.level }}
                    {{ skill.verified ? "" : ` · ${$t("page.research.skillUnverified")}` }}
                  </n-tag>
                </div>
                <p
                  v-if="profile.available_from || profile.available_until"
                  class="aira-type-meta mb-0 mt-3"
                >
                  {{ $t("page.research.executorAvailabilityWindow", {
                    from: formatDate(profile.available_from),
                    until: formatDate(profile.available_until),
                  }) }}
                </p>
                <p v-if="profile.notes" class="aira-type-meta mb-0 mt-3 whitespace-pre-wrap">
                  {{ profile.notes }}
                </p>
              </div>
              <n-button size="small" @click="beginEdit(profile)">
                {{ $t("common.edit") }}
              </n-button>
            </div>
          </article>
        </div>
        <n-empty v-else class="py-8" :description="$t('page.research.noHumanExecutorProfiles')" />
      </template>

      <template v-else-if="!preview">
        <n-form label-placement="top">
          <n-form-item :label="$t('page.research.humanExecutor')" required>
            <n-select
              v-model:value="userId"
              :options="editingId ? memberOptions : availableMemberOptions"
              :disabled="Boolean(editingId)"
              filterable
            />
          </n-form-item>
          <div class="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
            <n-form-item :label="$t('page.research.executorAvailability')" required>
              <n-select v-model:value="availability" :options="availabilityOptions" />
            </n-form-item>
            <n-form-item :label="$t('page.research.executorCapacity')" required>
              <n-input-number v-model:value="maxConcurrentItems" :min="1" :max="100" />
            </n-form-item>
            <n-form-item :label="$t('page.research.availableFrom')">
              <n-date-picker v-model:value="availableFrom" type="datetime" clearable class="w-full" />
            </n-form-item>
            <n-form-item :label="$t('page.research.availableUntil')">
              <n-date-picker v-model:value="availableUntil" type="datetime" clearable class="w-full" />
            </n-form-item>
          </div>

          <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div>
              <div class="aira-type-label">{{ $t("page.research.executorSkills") }}</div>
              <div class="aira-type-meta mt-1">{{ $t("page.research.executorSkillsHint") }}</div>
            </div>
            <n-button size="small" @click="addSkill">
              {{ $t("page.research.addExecutorSkill") }}
            </n-button>
          </div>
          <div v-if="skills.length" class="space-y-3">
            <div v-for="(skill, index) in skills" :key="skill.localId" class="human-executor-skill">
              <div class="grid grid-cols-1 gap-x-3 sm:grid-cols-2">
                <n-form-item :label="$t('page.research.skillKey')" required>
                  <n-input v-model:value="skill.key" placeholder="western_blot" />
                </n-form-item>
                <n-form-item :label="$t('page.research.skillName')" required>
                  <n-input v-model:value="skill.name" />
                </n-form-item>
                <n-form-item :label="$t('page.research.skillLevel')" required>
                  <n-input-number v-model:value="skill.level" :min="1" :max="5" />
                </n-form-item>
                <n-form-item :label="$t('page.research.skillExpiresAt')">
                  <n-date-picker v-model:value="skill.expiresAt" type="datetime" clearable class="w-full" />
                </n-form-item>
              </div>
              <div class="flex flex-wrap items-center justify-between gap-3">
                <n-checkbox v-model:checked="skill.verified">
                  {{ $t("page.research.skillVerified") }}
                </n-checkbox>
                <n-button size="tiny" quaternary type="error" @click="removeSkill(index)">
                  {{ $t("common.delete") }}
                </n-button>
              </div>
            </div>
          </div>
          <n-empty v-else size="small" class="mb-4" :description="$t('page.research.noExecutorSkills')" />

          <n-form-item :label="$t('page.research.executorNotes')">
            <n-input v-model:value="notes" type="textarea" :rows="3" />
          </n-form-item>
          <n-form-item :label="$t('page.research.changeReason')">
            <n-input v-model:value="reason" :placeholder="$t('page.research.changeReasonPlaceholder')" />
          </n-form-item>
        </n-form>
      </template>

      <template v-else>
        <section class="human-executor-preview">
          <div class="aira-type-eyebrow">{{ $t("page.research.previewImpact") }}</div>
          <h3 class="aira-type-card-title mb-0 mt-2">{{ userLabel(preview.executor) }}</h3>
          <dl class="human-executor-facts mt-4">
            <div>
              <dt>{{ $t("page.research.executorAvailability") }}</dt>
              <dd>{{ availabilityLabel(availability) }}</dd>
            </div>
            <div>
              <dt>{{ $t("page.research.executorCapacity") }}</dt>
              <dd>{{ maxConcurrentItems }}</dd>
            </div>
            <div>
              <dt>{{ $t("page.research.executorSkills") }}</dt>
              <dd>{{ skills.length }}</dd>
            </div>
          </dl>
          <n-alert type="warning" class="mt-4">
            {{ $t("page.research.executorProfileConfirmationHint") }}
          </n-alert>
        </section>
      </template>
    </n-spin>

    <template #footer>
      <div class="flex flex-wrap justify-end gap-2">
        <n-button @click="handleBack">
          {{ editing ? $t("page.research.backToHumanExecutors") : $t("common.close") }}
        </n-button>
        <n-button
          v-if="editing && !preview"
          type="primary"
          :disabled="!canPreview"
          :loading="submitting"
          @click="previewChange"
        >
          {{ $t("page.research.previewAction") }}
        </n-button>
        <n-button v-else-if="editing && preview" type="primary" :loading="submitting" @click="confirmChange">
          {{ $t("page.research.confirmHumanExecutorProfile") }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import type {
  ResearchHumanExecutorProfile,
  ResearchHumanExecutorProfileDraft,
  ResearchHumanExecutorProfilePreview,
  ResearchHumanExecutorUser,
} from "@/service/api/research-human-executors"
import {
  fetchResearchHumanExecutorProfiles,
  previewResearchHumanExecutorProfile,
  updateResearchHumanExecutorProfile,
} from "@/service/api/research-human-executors"
import { $t } from "@airalogy/shared/locales"
import { nanoid } from "nanoid"

interface SkillEditor {
  localId: string
  key: string
  name: string
  level: number
  verified: boolean
  expiresAt: number | null
}

const props = defineProps<{ labId: string }>()
const emit = defineEmits<{ updated: [] }>()

const visible = ref(false)
const loading = ref(false)
const submitting = ref(false)
const editing = ref(false)
const editingId = ref("")
const profiles = ref<ResearchHumanExecutorProfile[]>([])
const members = ref<ResearchHumanExecutorUser[]>([])
const preview = ref<ResearchHumanExecutorProfilePreview | null>(null)
const userId = ref("")
const availability = ref<"available" | "unavailable">("available")
const availableFrom = ref<number | null>(null)
const availableUntil = ref<number | null>(null)
const maxConcurrentItems = ref(1)
const skills = ref<SkillEditor[]>([])
const notes = ref("")
const reason = ref("")

const memberOptions = computed(() => members.value.map(user => ({
  label: userLabel(user),
  value: user.id,
})))
const availableMemberOptions = computed(() => {
  const configured = new Set(profiles.value.map(profile => profile.user_id))
  return memberOptions.value.filter(option => !configured.has(option.value))
})
const availabilityOptions = computed(() => [
  { label: $t("page.research.executorAvailable"), value: "available" },
  { label: $t("page.research.executorUnavailable"), value: "unavailable" },
])
const canPreview = computed(() => {
  if (!userId.value || maxConcurrentItems.value < 1)
    return false
  if (availableFrom.value && availableUntil.value && availableFrom.value >= availableUntil.value)
    return false
  const normalizedKeys = skills.value.map(skill => skill.key.trim().toLowerCase())
  return skills.value.every(skill => /^[a-z0-9][a-z0-9._-]{1,63}$/.test(skill.key.trim().toLowerCase()) && skill.name.trim())
    && new Set(normalizedKeys).size === normalizedKeys.length
})

function userLabel(user: ResearchHumanExecutorUser) {
  return user.name ? `${user.name} (@${user.username})` : `@${user.username}`
}

function availabilityLabel(value: "available" | "unavailable") {
  return value === "available"
    ? $t("page.research.executorAvailable")
    : $t("page.research.executorUnavailable")
}

function toTimestamp(value: string | null) {
  return value ? new Date(value).getTime() : null
}

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleString() : $t("page.research.executorWindowOpen")
}

function toIso(value: number | null) {
  return value ? new Date(value).toISOString() : null
}

async function load() {
  loading.value = true
  try {
    const result = await fetchResearchHumanExecutorProfiles(props.labId)
    profiles.value = result.items
    members.value = result.members
  }
  finally {
    loading.value = false
  }
}

function open() {
  visible.value = true
  void load()
}

function beginCreate() {
  resetEditor()
  editing.value = true
  userId.value = availableMemberOptions.value[0]?.value || ""
}

function beginEdit(profile: ResearchHumanExecutorProfile) {
  resetEditor()
  editing.value = true
  editingId.value = profile.id
  userId.value = profile.user_id
  availability.value = profile.availability
  availableFrom.value = toTimestamp(profile.available_from)
  availableUntil.value = toTimestamp(profile.available_until)
  maxConcurrentItems.value = profile.max_concurrent_items
  skills.value = profile.skills.map(skill => ({
    localId: nanoid(),
    key: skill.key,
    name: skill.name,
    level: skill.level,
    verified: skill.verified,
    expiresAt: toTimestamp(skill.expires_at),
  }))
  notes.value = profile.notes
}

function addSkill() {
  skills.value.push({
    localId: nanoid(),
    key: "",
    name: "",
    level: 1,
    verified: false,
    expiresAt: null,
  })
}

function removeSkill(index: number) {
  skills.value.splice(index, 1)
}

function resetEditor() {
  editing.value = false
  editingId.value = ""
  preview.value = null
  userId.value = ""
  availability.value = "available"
  availableFrom.value = null
  availableUntil.value = null
  maxConcurrentItems.value = 1
  skills.value = []
  notes.value = ""
  reason.value = ""
}

function payload(): ResearchHumanExecutorProfileDraft {
  const profile = profiles.value.find(item => item.id === editingId.value)
  return {
    lab_id: props.labId,
    user_id: userId.value,
    expected_revision: profile?.revision || 0,
    availability: availability.value,
    available_from: toIso(availableFrom.value),
    available_until: toIso(availableUntil.value),
    max_concurrent_items: maxConcurrentItems.value,
    skills: skills.value.map(skill => ({
      key: skill.key.trim().toLowerCase(),
      name: skill.name.trim(),
      level: skill.level,
      verified: skill.verified,
      expires_at: toIso(skill.expiresAt),
    })),
    notes: notes.value.trim(),
    reason: reason.value.trim(),
  }
}

async function previewChange() {
  submitting.value = true
  try {
    preview.value = await previewResearchHumanExecutorProfile(payload())
  }
  finally {
    submitting.value = false
  }
}

async function confirmChange() {
  if (!preview.value)
    return
  submitting.value = true
  try {
    await updateResearchHumanExecutorProfile(userId.value, {
      ...payload(),
      preview_digest: preview.value.preview_digest,
    })
    window.$message?.success($t("page.research.humanExecutorProfileSaved"))
    resetEditor()
    await load()
    emit("updated")
  }
  finally {
    submitting.value = false
  }
}

function handleBack() {
  if (preview.value) {
    preview.value = null
    return
  }
  if (editing.value) {
    resetEditor()
    return
  }
  visible.value = false
}
</script>

<style scoped>
.human-executor-card,
.human-executor-preview,
.human-executor-skill {
  border: 1px solid rgb(229 231 235);
  border-radius: 0.85rem;
  padding: 1rem;
}

.human-executor-skill {
  background: rgb(248 250 252);
}

.human-executor-facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr));
  gap: 0.75rem;
  margin-bottom: 0;
}

.human-executor-facts > div {
  border-radius: 0.7rem;
  background: rgb(248 250 252);
  padding: 0.75rem;
}

.human-executor-facts dt {
  color: rgb(107 114 128);
  font-size: 0.75rem;
}

.human-executor-facts dd {
  margin: 0.25rem 0 0;
  font-weight: 600;
}
</style>

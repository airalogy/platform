<template>
  <section class="rounded-3 border border-gray-200 bg-white p-5 shadow-sm">
    <div class="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
      <div>
        <div class="text-xs text-gray-500 font-semibold tracking-wide uppercase">
          {{ $t("page.home.workbench.eyebrow") }}
        </div>
        <h1 class="mb-0 mt-1 text-2xl font-semibold">
          {{ $t("page.home.workbench.title", { name: displayName }) }}
        </h1>
        <p class="mb-0 mt-2 text-sm text-gray-500 leading-6">
          {{ $t("page.home.workbench.description") }}
        </p>
      </div>
      <n-tag v-if="instanceStore.aiEnabled" type="info" round>
        {{ $t("page.home.workbench.aiAvailable") }}
      </n-tag>
    </div>

    <n-alert v-if="loadError" type="error" class="mt-4" :title="$t('page.home.workbench.loadError')">
      <n-button class="mt-2" size="small" @click="loadWorkbench">
        {{ $t("common.retry") }}
      </n-button>
    </n-alert>

    <n-spin v-else :show="loading" class="mt-5 min-h-44">
      <div class="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(240px,1fr)]">
        <div class="rounded-3 border border-primary/25 from-primary/8 to-sky-50 bg-gradient-to-br p-5">
          <template v-if="latestDraft?.protocol">
            <div class="text-xs text-primary font-semibold tracking-wide uppercase">
              {{ $t("page.home.workbench.continueLabel") }}
            </div>
            <h2 class="mb-0 mt-2 text-xl font-semibold">
              {{ $t("page.home.workbench.continueDraftTitle") }}
            </h2>
            <p class="mb-0 mt-2 text-sm text-gray-600">
              {{ latestDraft.protocol.lab.name }} / {{ latestDraft.protocol.project.name }} /
              {{ latestDraft.protocol.name }}
            </p>
            <p class="mb-0 mt-2 text-xs text-gray-500">
              {{ $t("page.home.workbench.savedOnDevice") }} ·
              <n-time :time="latestDraft.timestamp" type="relative" />
            </p>
            <div class="mt-5 flex flex-wrap gap-2">
              <n-button type="primary" @click="continueDraft(latestDraft)">
                {{ $t("page.home.workbench.continueAction") }}
              </n-button>
              <n-button secondary @click="openProtocol(latestDraft.protocol)">
                {{ $t("page.home.workbench.viewProtocolAction") }}
              </n-button>
            </div>
          </template>

          <template v-else-if="recentProtocol">
            <div class="text-xs text-primary font-semibold tracking-wide uppercase">
              {{ $t("page.home.workbench.nextTaskLabel") }}
            </div>
            <h2 class="mb-0 mt-2 text-xl font-semibold">
              {{ $t("page.home.workbench.startRecordTitle") }}
            </h2>
            <p class="mb-0 mt-2 text-sm text-gray-600">
              {{ recentProtocol.lab.name }} / {{ recentProtocol.project.name }} /
              {{ recentProtocol.name }}
            </p>
            <div class="mt-5 flex flex-wrap gap-2">
              <n-button type="primary" @click="startRecord(recentProtocol)">
                {{ $t("page.home.workbench.startRecordAction") }}
              </n-button>
              <n-button secondary @click="openProtocol(recentProtocol)">
                {{ $t("page.home.workbench.viewProtocolAction") }}
              </n-button>
            </div>
          </template>

          <template v-else-if="protocolCreationProject">
            <div class="text-xs text-primary font-semibold tracking-wide uppercase">
              {{ $t("page.home.workbench.nextTaskLabel") }}
            </div>
            <h2 class="mb-0 mt-2 text-xl font-semibold">
              {{ $t("page.home.workbench.createProtocolTitle") }}
            </h2>
            <p class="mb-0 mt-2 text-sm text-gray-600">
              {{ protocolCreationProject.lab_name }} / {{ protocolCreationProject.name }}
            </p>
            <div class="mt-5 flex flex-wrap gap-2">
              <n-button type="primary" @click="createProtocol('template')">
                {{ $t("page.home.workbench.fromTemplateAction") }}
              </n-button>
              <n-button v-if="instanceStore.aiEnabled" secondary @click="createProtocol('ai')">
                {{ $t("page.home.workbench.askAiraAction") }}
              </n-button>
            </div>
          </template>

          <template v-else-if="recentProject">
            <div class="text-xs text-primary font-semibold tracking-wide uppercase">
              {{ $t("page.home.workbench.nextTaskLabel") }}
            </div>
            <h2 class="mb-0 mt-2 text-xl font-semibold">
              {{ $t("page.home.workbench.openProjectTitle") }}
            </h2>
            <p class="mb-0 mt-2 text-sm text-gray-600 leading-6">
              {{ $t("page.home.workbench.openProjectDescription", { name: recentProject.name }) }}
            </p>
            <n-button class="mt-5" type="primary" @click="openProject(recentProject)">
              {{ $t("page.home.workbench.openProjectAction") }}
            </n-button>
          </template>

          <template v-else>
            <div class="text-xs text-primary font-semibold tracking-wide uppercase">
              {{ $t("page.home.workbench.nextTaskLabel") }}
            </div>
            <h2 class="mb-0 mt-2 text-xl font-semibold">
              {{ $t("page.home.workbench.createProjectTitle") }}
            </h2>
            <p class="mb-0 mt-2 text-sm text-gray-600 leading-6">
              {{ $t("page.home.workbench.createProjectDescription") }}
            </p>
            <create-project-modal
              class="mt-5"
              :button-props="{ type: 'primary' }"
              :show-icon="false"
              :trigger="$t('page.home.workbench.createProjectAction')"
              @modal:new-project="handleProjectCreated"
            />
          </template>
        </div>

        <div class="rounded-3 border border-gray-200 bg-gray-50 p-5">
          <div class="text-xs text-gray-500 font-semibold tracking-wide uppercase">
            {{ $t("page.home.workbench.attentionLabel") }}
          </div>
          <div class="mt-3 flex items-baseline gap-2">
            <span class="text-3xl font-semibold">{{ validDrafts.length }}</span>
            <span class="text-sm text-gray-600">
              {{ $t("page.home.workbench.draftsCount", { count: validDrafts.length }) }}
            </span>
          </div>
          <p class="mb-0 mt-2 text-sm text-gray-500 leading-6">
            {{ validDrafts.length
              ? $t("page.home.workbench.draftsHint")
              : $t("page.home.workbench.noDraftsHint") }}
          </p>
        </div>
      </div>

      <div class="mt-5">
        <h2 class="mb-3 text-base font-semibold">
          {{ $t("page.home.workbench.quickActions") }}
        </h2>
        <div class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          <button
            v-if="recentProtocol"
            type="button"
            class="task-action"
            @click="startRecord(recentProtocol)"
          >
            <span class="task-action__title">{{ $t("page.home.workbench.startRecordAction") }}</span>
            <span class="task-action__description">{{ recentProtocol.name }}</span>
          </button>
          <button
            v-if="protocolCreationProject"
            type="button"
            class="task-action"
            @click="createProtocol('template')"
          >
            <span class="task-action__title">{{ $t("page.home.workbench.fromTemplateAction") }}</span>
            <span class="task-action__description">{{ protocolCreationProject.name }}</span>
          </button>
          <button
            v-if="instanceStore.aiEnabled && protocolCreationProject"
            type="button"
            class="task-action task-action--ai"
            @click="createProtocol('ai')"
          >
            <span class="task-action__title">{{ $t("page.home.workbench.askAiraAction") }}</span>
            <span class="task-action__description">{{ $t("page.home.workbench.askAiraDescription") }}</span>
          </button>
          <button
            v-if="managedProject"
            type="button"
            class="task-action"
            @click="manageProjectMembers(managedProject)"
          >
            <span class="task-action__title">{{ $t("page.home.workbench.manageProjectAction") }}</span>
            <span class="task-action__description">{{ managedProject.name }}</span>
          </button>
          <button
            v-if="ownedProtocol"
            type="button"
            class="task-action"
            @click="openProtocol(ownedProtocol)"
          >
            <span class="task-action__title">{{ $t("page.home.workbench.reviewProtocolAction") }}</span>
            <span class="task-action__description">{{ ownedProtocol.name }}</span>
          </button>
          <button
            v-if="managedLab"
            type="button"
            class="task-action"
            @click="manageLabMembers(managedLab)"
          >
            <span class="task-action__title">{{ $t("page.home.workbench.manageLabAction") }}</span>
            <span class="task-action__description">{{ managedLab.name }}</span>
          </button>
          <button
            v-if="isGlobalAdministrator"
            type="button"
            class="task-action"
            @click="openOperationsHelp"
          >
            <span class="task-action__title">{{ $t("page.home.workbench.operationsAction") }}</span>
            <span class="task-action__description">{{ $t("page.home.workbench.operationsDescription") }}</span>
          </button>
        </div>
      </div>
    </n-spin>
  </section>
</template>

<script setup lang="ts">
import type { ProtocolModels } from "@airalogy/shared/types"
import { checkProjectActionPermission, ProjectAction } from "@/composables/useProjectPermissions"
import { LabRole, ProjectRole } from "@/enum"
import { getProtocolInfo } from "@/service/api/protocol"
import { fetchUserLabs, fetchUserProjects, fetchUserProtocols } from "@/service/api/users"
import { useAuthStore } from "@/store/modules/auth"
import { useInstanceStore } from "@/store/modules/instance"
import { listRecordDrafts, type RecordDraft } from "@/utils/recordDrafts"
import CreateProjectModal from "@/views/projects/modules/create-project-modal.vue"
import { useLoading } from "@airalogy/composables"
import { nanoid } from "nanoid"
import { useRouter } from "vue-router"

interface ResolvedDraft extends RecordDraft {
  protocol: ProtocolModels.ProjectProtocolInfo
}

const authStore = useAuthStore()
const instanceStore = useInstanceStore()
const router = useRouter()
const { loading, startLoading, endLoading } = useLoading(true)

const projects = ref<Api.Project.MyProjectInfo[]>([])
const labs = ref<Api.Lab.UsersLabInfo[]>([])
const protocols = ref<ProtocolModels.ProjectProtocolInfo[]>([])
const validDrafts = ref<ResolvedDraft[]>([])
const loadError = ref(false)

const displayName = computed(() => authStore.userInfo.name || authStore.userInfo.username)
const recentProject = computed(() => projects.value[0] || null)
const protocolCreationProject = computed(() => projects.value.find(project =>
  checkProjectActionPermission(project.user_role, project.type, ProjectAction.CREATE_PROTOCOL),
) || null)
const recentProtocol = computed(() => protocols.value.find(canSubmitRecordForProtocol) || null)
const latestDraft = computed(() => validDrafts.value[0] || null)
const managedProject = computed(() => projects.value.find(project =>
  project.user_role === ProjectRole.OWNER || project.user_role === ProjectRole.MANAGER,
) || null)
const managedLab = computed(() => labs.value.find(lab =>
  lab.user_role === LabRole.OWNER || lab.user_role === LabRole.MANAGER,
) || null)
const ownedProtocol = computed(() => protocols.value.find(protocol =>
  String(protocol.user_id) === String(authStore.userInfo.id),
) || null)
const isGlobalAdministrator = computed(() =>
  authStore.userInfo.roles?.some(role => role === "R_ADMIN" || role === "R_SUPER") ?? false,
)

function canSubmitRecordForProtocol(protocol: ProtocolModels.ProjectProtocolInfo) {
  const project = projects.value.find(item =>
    String(item.id) === String(protocol.project.id)
    || item.uid === protocol.project.uid,
  )
  return Boolean(project && checkProjectActionPermission(
    project.user_role,
    project.type,
    ProjectAction.SUBMIT_DATA_TO_OTHERS,
  ))
}

async function loadWorkbench() {
  if (!authStore.userInfo.id) {
    return
  }
  startLoading()
  loadError.value = false
  try {
    const userId = authStore.userInfo.id
    const [projectResult, labResult, protocolResult] = await Promise.all([
      fetchUserProjects(userId, { page: 1, pageSize: 10, sortedBy: "updated_at" }),
      fetchUserLabs(userId, { page: 1, pageSize: 10, sortedBy: "updated_at" }),
      fetchUserProtocols(userId, { page: 1, pageSize: 10, sortedBy: "updated_at" }),
    ])
    projects.value = projectResult?.projects || []
    labs.value = labResult?.labs || []
    protocols.value = protocolResult?.protocols || []

    const localDrafts = listRecordDrafts(userId).slice(0, 10)
    const draftResults = await Promise.allSettled(
      localDrafts.map(async (draft) => {
        const result = await getProtocolInfo(draft.protocolId, undefined, false)
        return result.data ? { ...draft, protocol: result.data } : null
      }),
    )
    validDrafts.value = draftResults
      .filter((result): result is PromiseFulfilledResult<ResolvedDraft | null> => result.status === "fulfilled")
      .map(result => result.value)
      .filter((draft): draft is ResolvedDraft => Boolean(draft))
      .filter(draft => canSubmitRecordForProtocol(draft.protocol))
      .sort((a, b) => b.timestamp - a.timestamp)
  }
  catch {
    loadError.value = true
  }
  finally {
    endLoading()
  }
}

function protocolRouteParams(protocol: ProtocolModels.ProjectProtocolInfo) {
  return {
    labUid: protocol.lab.uid,
    projectUid: protocol.project.uid,
    protocolUid: protocol.uid,
  }
}

function startRecord(protocol: ProtocolModels.ProjectProtocolInfo) {
  void router.push({ name: "add-protocol-record", params: protocolRouteParams(protocol) })
}

function continueDraft(draft: ResolvedDraft) {
  void router.push({
    name: "add-protocol-record",
    params: protocolRouteParams(draft.protocol),
    query: { resumeDraft: "true" },
  })
}

function openProtocol(protocol: ProtocolModels.ProjectProtocolInfo) {
  void router.push({ name: "protocol-detail", params: protocolRouteParams(protocol) })
}

function createProtocol(mode: "template" | "ai") {
  if (!protocolCreationProject.value || (mode === "ai" && !instanceStore.aiEnabled)) {
    return
  }
  void router.push({
    name: "protocol-editor",
    params: {
      labUid: protocolCreationProject.value.lab_uid,
      projectUid: protocolCreationProject.value.uid,
      protocolUid: `protocol-${nanoid()}`,
    },
    query: mode === "ai" ? { show_ai_create: "true" } : { show_template: "true" },
  })
}

function openProject(project: Api.Project.MyProjectInfo) {
  void router.push({
    name: "project-protocols",
    params: { labUid: project.lab_uid, projectUid: project.uid },
  })
}

function manageProjectMembers(project: Api.Project.MyProjectInfo) {
  void router.push({
    name: "project-members",
    params: { labUid: project.lab_uid, projectUid: project.uid },
  })
}

function manageLabMembers(lab: Api.Lab.UsersLabInfo) {
  void router.push({ name: "lab-members", params: { labUid: lab.uid } })
}

function openOperationsHelp() {
  void router.push({ name: "help-center" })
}

function handleProjectCreated(project: Api.Project.MyProjectInfo) {
  void router.push({
    name: "project-protocols",
    params: { labUid: project.lab_uid, projectUid: project.uid },
  })
}

onMounted(loadWorkbench)
</script>

<style scoped>
.task-action {
  display: flex;
  min-height: 5.25rem;
  flex-direction: column;
  align-items: flex-start;
  justify-content: center;
  border: 1px solid rgb(229 231 235);
  border-radius: 0.75rem;
  background: white;
  padding: 0.875rem 1rem;
  text-align: left;
  transition: border-color 160ms ease, box-shadow 160ms ease, transform 160ms ease;
}

.task-action:hover,
.task-action:focus-visible {
  border-color: rgb(var(--primary-color) / 45%);
  box-shadow: 0 8px 22px rgb(15 23 42 / 8%);
  outline: none;
  transform: translateY(-1px);
}

.task-action--ai {
  background: linear-gradient(135deg, rgb(var(--primary-color) / 8%), rgb(14 165 233 / 5%));
}

.task-action__title {
  font-size: 0.875rem;
  font-weight: 600;
}

.task-action__description {
  margin-top: 0.25rem;
  color: rgb(107 114 128);
  font-size: 0.8125rem;
}
</style>

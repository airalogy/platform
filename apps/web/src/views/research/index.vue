<template>
  <div class="research-page py-8">
    <header class="research-hero">
      <div class="min-w-0">
        <div class="aira-type-eyebrow aira-type-eyebrow--accent">
          {{ $t("page.research.eyebrow") }}
        </div>
        <h1 class="aira-type-page-title mb-0 mt-1">
          {{ projectContext ? $t("page.research.projectTitle") : $t("page.research.title") }}
        </h1>
        <p class="aira-type-body aira-text-secondary mb-0 mt-2 max-w-3xl">
          {{ $t("page.research.description") }}
        </p>
      </div>
      <div class="flex shrink-0 flex-wrap items-center gap-2">
        <n-button quaternary :loading="loading" @click="loadCurrentView">
          <template #icon><n-icon><icon-tabler-refresh /></n-icon></template>
          {{ $t("page.research.refresh") }}
        </n-button>
        <create-research-task-modal
          v-if="activeView === 'tasks'"
          :project="projectContext"
          @created="openTask"
        />
      </div>
    </header>

    <n-alert v-if="loadError" type="error" class="mt-5" :title="$t('page.research.loadError')">
      <n-button size="small" class="mt-2" @click="loadCurrentView">
        {{ $t("common.retry") }}
      </n-button>
    </n-alert>

    <n-tabs
      v-if="!projectContext"
      :value="activeView"
      type="line"
      animated
      class="mt-6"
      @update:value="handleViewChange"
    >
      <n-tab name="tasks">{{ $t("page.research.tasks") }}</n-tab>
      <n-tab name="work-items">
        {{ $t("page.research.workItems") }}
        <n-badge v-if="workItemCount" :value="workItemCount" :max="99" class="ml-1" />
      </n-tab>
      <n-tab name="approvals">
        {{ $t("page.research.approvals") }}
        <n-badge v-if="approvalCount" :value="approvalCount" :max="99" class="ml-1" />
      </n-tab>
    </n-tabs>

    <n-spin :show="loading" class="mt-5 min-h-70">
      <template v-if="activeView === 'tasks'">
        <div v-if="tasks.length" class="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <button
            v-for="task in tasks"
            :key="task.id"
            type="button"
            class="research-card"
            @click="openTask(task)"
          >
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div class="min-w-0">
                <div class="aira-type-meta">
                  {{ task.lab.name }} / {{ task.project.name }}
                </div>
                <h2 class="aira-type-card-title mb-0 mt-1 line-clamp-2">
                  {{ task.title }}
                </h2>
              </div>
              <n-tag :type="statusType(task.status)" round size="small">
                {{ taskStatusLabel(task.status) }}
              </n-tag>
            </div>
            <p class="aira-type-body aira-text-secondary mb-0 mt-3 line-clamp-3">
              {{ task.goal }}
            </p>
            <div class="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 aira-type-meta">
              <span>{{ $t("page.research.owner") }} · {{ task.owner?.name || task.owner?.username }}</span>
              <span v-if="task.open_work_items">
                {{ $t("page.research.openWorkCount", { count: task.open_work_items }) }}
              </span>
              <span v-if="task.latest_run">
                {{ runStatusLabel(task.latest_run.status) }}
              </span>
              <n-time :time="new Date(task.updated_at)" type="relative" />
            </div>
          </button>
        </div>
        <n-empty v-else-if="!loading" class="research-empty" :description="$t('page.research.noTasks')">
          <template #extra>
            <create-research-task-modal :project="projectContext" @created="openTask" />
          </template>
        </n-empty>
      </template>

      <template v-else-if="activeView === 'work-items'">
        <div v-if="workItems.length" class="space-y-4">
          <article v-for="item in workItems" :key="item.id" class="research-card">
            <div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div class="min-w-0 flex-1">
                <div class="flex flex-wrap items-center gap-2">
                  <n-tag :type="workItemType(item.status)" round size="small">
                    {{ workItemStatusLabel(item.status) }}
                  </n-tag>
                  <span class="aira-type-meta">
                    {{ item.lab.name }} / {{ item.project.name }}
                  </span>
                </div>
                <button type="button" class="mt-2 text-left" @click="openTaskById(item.task.id)">
                  <h2 class="aira-type-card-title mb-0 hover:text-primary">
                    {{ item.action.title }}
                  </h2>
                </button>
                <p class="aira-type-body aira-text-secondary mb-0 mt-2 whitespace-pre-wrap">
                  {{ item.instructions || item.task.goal }}
                </p>
                <div class="mt-3 aira-type-meta">
                  {{ $t("page.research.partOfTask") }} · {{ item.task.title }}
                  <template v-if="item.due_at">
                    · {{ $t("page.research.due") }} <n-time :time="new Date(item.due_at)" />
                  </template>
                </div>
              </div>
              <div class="flex shrink-0 flex-wrap gap-2">
                <n-button secondary @click="openTaskById(item.task.id)">
                  {{ $t("page.research.viewTask") }}
                </n-button>
                <n-button
                  v-if="canExecute(item)"
                  type="primary"
                  :loading="startingId === item.id"
                  @click="executeWorkItem(item)"
                >
                  {{ $t("page.research.executeProtocol") }}
                </n-button>
              </div>
            </div>
          </article>
        </div>
        <n-empty v-else-if="!loading" class="research-empty" :description="$t('page.research.noWorkItems')" />
      </template>

      <template v-else>
        <div v-if="approvals.length" class="space-y-4">
          <article v-for="approval in approvals" :key="approval.id" class="research-card">
            <div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div class="min-w-0 flex-1">
                <div class="flex flex-wrap items-center gap-2">
                  <n-tag type="warning" round size="small">
                    {{ $t("page.research.approvalPending") }}
                  </n-tag>
                  <span class="aira-type-meta">
                    {{ approval.lab.name }} / {{ approval.project.name }}
                  </span>
                </div>
                <button type="button" class="mt-2 text-left" @click="openTaskById(approval.task.id)">
                  <h2 class="aira-type-card-title mb-0 hover:text-primary">
                    {{ approval.action.title }}
                  </h2>
                </button>
                <p class="aira-type-body aira-text-secondary mb-0 mt-2 whitespace-pre-wrap">
                  {{ approval.action.description || approval.reason }}
                </p>
                <div class="mt-3 flex flex-wrap gap-x-4 gap-y-1 aira-type-meta">
                  <span>{{ $t("page.research.partOfTask") }} · {{ approval.task.title }}</span>
                  <span v-if="approval.action.protocol">
                    {{ approval.action.protocol.name }} · v{{ approval.action.protocol.version }}
                  </span>
                  <span><n-time :time="new Date(approval.requested_at)" type="relative" /></span>
                </div>
              </div>
              <div class="flex shrink-0 flex-wrap gap-2">
                <n-button secondary @click="openTaskById(approval.task.id)">
                  {{ $t("page.research.viewTask") }}
                </n-button>
                <research-approval-actions
                  :approval="approval"
                  :action-revision="approval.action.revision"
                  @decided="loadCurrentView"
                />
              </div>
            </div>
          </article>
        </div>
        <n-empty v-else-if="!loading" class="research-empty" :description="$t('page.research.noApprovals')" />
      </template>
    </n-spin>

    <div v-if="totalCount > pageSize" class="mt-6 flex justify-end">
      <n-pagination
        v-model:page="page"
        :page-size="pageSize"
        :item-count="totalCount"
        @update:page="loadCurrentView"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import type {
  HumanWorkItemStatus,
  ResearchApprovalDetail,
  ResearchRunStatus,
  ResearchTaskDetail,
  ResearchTaskStatus,
  ResearchTaskSummary,
  ResearchWorkItemDetail,
} from "@/service/api/research-tasks"
import type { TagProps } from "naive-ui"
import { getProjectInfo } from "@/service/api/projects"
import {
  fetchResearchApprovals,
  fetchResearchTasks,
  fetchResearchWorkItems,
  startResearchWorkItem,
} from "@/service/api/research-tasks"
import { $t } from "@airalogy/shared/locales"
import { useRoute, useRouter } from "vue-router"
import CreateResearchTaskModal from "./components/create-research-task-modal.vue"
import ResearchApprovalActions from "./components/research-approval-actions.vue"

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const loadError = ref(false)
const tasks = ref<ResearchTaskSummary[]>([])
const workItems = ref<ResearchWorkItemDetail[]>([])
const approvals = ref<ResearchApprovalDetail[]>([])
const workItemCount = ref(0)
const approvalCount = ref(0)
const totalCount = ref(0)
const page = ref(1)
const pageSize = 20
const startingId = ref("")
const projectContext = ref<Api.Project.MyProjectInfo | null>(null)

const activeView = computed<"tasks" | "work-items" | "approvals">(() => {
  if (route.name === "research-work-items")
    return "work-items"
  if (route.name === "research-approvals")
    return "approvals"
  return "tasks"
})

async function loadProjectContext() {
  if (route.name !== "project-research") {
    projectContext.value = null
    return
  }
  const { labUid, projectUid } = route.params as Record<string, string>
  projectContext.value = await getProjectInfo({ labUid, projectUid })
}

async function loadCurrentView() {
  loading.value = true
  loadError.value = false
  try {
    await loadProjectContext()
    if (activeView.value === "tasks") {
      const result = await fetchResearchTasks({
        projectId: projectContext.value ? String(projectContext.value.id) : undefined,
        page: page.value,
        pageSize,
      })
      tasks.value = result.tasks
      totalCount.value = result.total_count
      if (!projectContext.value) {
        const [assigned, pending] = await Promise.all([
          fetchResearchWorkItems({ page: 1, pageSize: 1 }),
          fetchResearchApprovals({ page: 1, pageSize: 1 }),
        ])
        workItemCount.value = assigned.total_count
        approvalCount.value = pending.total_count
      }
    }
    else if (activeView.value === "work-items") {
      const result = await fetchResearchWorkItems({ page: page.value, pageSize })
      workItems.value = result.work_items
      totalCount.value = result.total_count
      workItemCount.value = result.total_count
      const pending = await fetchResearchApprovals({ page: 1, pageSize: 1 })
      approvalCount.value = pending.total_count
    }
    else {
      const result = await fetchResearchApprovals({ page: page.value, pageSize })
      approvals.value = result.approvals
      totalCount.value = result.total_count
      approvalCount.value = result.total_count
      const assigned = await fetchResearchWorkItems({ page: 1, pageSize: 1 })
      workItemCount.value = assigned.total_count
    }
  }
  catch {
    loadError.value = true
  }
  finally {
    loading.value = false
  }
}

function handleViewChange(view: "tasks" | "work-items" | "approvals") {
  page.value = 1
  const name = view === "tasks"
    ? "research-tasks"
    : view === "work-items"
      ? "research-work-items"
      : "research-approvals"
  void router.push({ name })
}

function openTask(task: ResearchTaskSummary | ResearchTaskDetail) {
  openTaskById(task.id)
}

function openTaskById(taskId: string) {
  void router.push({ name: "research-task-detail", params: { taskId } })
}

function canExecute(item: ResearchWorkItemDetail) {
  return Boolean(
    item.action.protocol
    && ["open", "in_progress", "changes_requested"].includes(item.status),
  )
}

async function executeWorkItem(item: ResearchWorkItemDetail) {
  const protocol = item.action.protocol
  if (!protocol)
    return
  startingId.value = item.id
  try {
    if (item.status === "open" || item.status === "changes_requested")
      await startResearchWorkItem(item.id, item.revision)
    await router.push({
      name: "add-protocol-record",
      params: {
        labUid: protocol.lab_uid || item.lab.uid,
        projectUid: protocol.project_uid || item.project.uid,
        protocolUid: protocol.uid,
      },
      query: { researchWorkItem: item.id },
    })
  }
  finally {
    startingId.value = ""
  }
}

function statusType(status: ResearchTaskStatus): TagProps["type"] {
  if (status === "completed")
    return "success"
  if (status === "failed" || status === "cancelled")
    return "error"
  if (status === "review_required")
    return "warning"
  if (status === "active")
    return "info"
  return "default"
}

function workItemType(status: HumanWorkItemStatus): TagProps["type"] {
  if (status === "accepted")
    return "success"
  if (status === "cancelled")
    return "error"
  if (status === "changes_requested")
    return "warning"
  return "info"
}

function taskStatusLabel(status: ResearchTaskStatus) {
  return $t(`page.research.taskStatus.${status}` as I18n.I18nKey)
}

function runStatusLabel(status: ResearchRunStatus) {
  return $t(`page.research.runStatus.${status}` as I18n.I18nKey)
}

function workItemStatusLabel(status: HumanWorkItemStatus) {
  return $t(`page.research.workItemStatus.${status}` as I18n.I18nKey)
}

watch(() => route.fullPath, () => {
  page.value = 1
  void loadCurrentView()
})
onMounted(loadCurrentView)
</script>

<style scoped>
.research-page {
  width: 100%;
}

.research-hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1.5rem;
  border: 1px solid rgb(219 234 254);
  border-radius: 1rem;
  background: linear-gradient(135deg, rgb(var(--primary-color) / 8%), white 68%);
  padding: clamp(1.25rem, 3vw, 2rem);
}

.research-card {
  display: block;
  width: 100%;
  border: 1px solid rgb(229 231 235);
  border-radius: 0.875rem;
  background: white;
  padding: 1.25rem;
  text-align: left;
  transition: border-color 160ms ease, box-shadow 160ms ease, transform 160ms ease;
}

button.research-card:hover,
button.research-card:focus-visible {
  border-color: rgb(var(--primary-color) / 45%);
  box-shadow: 0 10px 28px rgb(15 23 42 / 8%);
  outline: none;
  transform: translateY(-1px);
}

.research-empty {
  min-height: 18rem;
  display: flex;
  align-items: center;
  justify-content: center;
}

@media (max-width: 48rem) {
  .research-hero {
    flex-direction: column;
  }
}
</style>

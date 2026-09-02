<template>
  <div class="knowledge-page py-8">
    <header class="knowledge-hero">
      <div class="min-w-0">
        <div class="aira-type-eyebrow aira-type-eyebrow--accent">
          {{ $t("page.knowledge.eyebrow") }}
        </div>
        <h1 class="aira-type-page-title mb-0 mt-1">
          {{ pageTitle }}
        </h1>
        <p class="aira-type-body aira-text-secondary mb-0 mt-2 max-w-3xl">
          {{ $t("page.knowledge.description") }}
        </p>
      </div>
      <div class="flex shrink-0 flex-wrap items-center gap-2">
        <n-button quaternary :loading="loading" @click="() => loadCurrentView()">
          <template #icon>
            <n-icon><icon-tabler-refresh /></n-icon>
          </template>
          {{ $t("page.knowledge.refresh") }}
        </n-button>
        <knowledge-editor-modal
          ref="editorRef"
          :scope="scope"
          :scope-label="scopeLabel"
          @saved="handleKnowledgeSaved"
        />
        <import-paper-modal
          :scope="scope"
          :scope-label="scopeLabel"
          @imported="handlePaperImported"
        />
      </div>
    </header>

    <n-alert class="mt-5" type="info" :title="$t('page.knowledge.privateByDesign')">
      {{ $t("page.knowledge.privateHint") }}
    </n-alert>

    <div class="knowledge-toolbar mt-5">
      <n-select
        v-if="!contextLocked"
        v-model:value="selectedScopeKey"
        class="min-w-56 flex-1 md:max-w-80"
        :options="scopeOptions"
        :loading="contextsLoading"
        :placeholder="$t('page.knowledge.scope')"
        @update:value="handleScopeChange"
      />
      <div v-else class="knowledge-scope-label">
        <n-icon><icon-tabler-folders /></n-icon>
        <span>{{ scopeLabel }}</span>
      </div>
      <n-input
        v-model:value="search"
        clearable
        class="min-w-56 flex-[2]"
        :placeholder="$t('page.knowledge.searchPlaceholder')"
        @keyup.enter="() => loadCurrentView()"
        @clear="() => loadCurrentView()"
      >
        <template #prefix>
          <n-icon><icon-tabler-search /></n-icon>
        </template>
      </n-input>
    </div>

    <n-alert v-if="loadError" type="error" class="mt-5" :title="$t('page.knowledge.loadError')">
      <n-button size="small" class="mt-2" @click="() => loadCurrentView()">
        {{ $t("common.retry") }}
      </n-button>
    </n-alert>

    <n-tabs v-model:value="activeView" type="line" animated class="mt-6" @update:value="() => loadCurrentView()">
      <n-tab name="papers">
        {{ $t("page.knowledge.papers") }}
      </n-tab>
      <n-tab name="items">
        {{ $t("page.knowledge.items") }}
      </n-tab>
    </n-tabs>

    <div v-if="activeView === 'items'" class="mt-4 flex flex-wrap gap-3">
      <n-select
        v-model:value="kindFilter"
        clearable
        class="w-44"
        :options="kindOptions"
        :placeholder="$t('page.knowledge.kind')"
        @update:value="() => loadCurrentView()"
      />
      <n-select
        v-model:value="stateFilter"
        clearable
        class="w-44"
        :options="stateOptions"
        :placeholder="$t('page.knowledge.state')"
        @update:value="() => loadCurrentView()"
      />
    </div>

    <n-spin :show="loading" class="mt-5 min-h-70">
      <template v-if="activeView === 'papers'">
        <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div v-if="collections.length" class="flex flex-wrap gap-2">
            <n-tag v-for="collection in collections" :key="collection.id" round>
              {{ collection.name }}
            </n-tag>
          </div>
          <n-button size="small" secondary @click="collectionModalVisible = true">
            <template #icon>
              <n-icon><icon-tabler-folder-plus /></n-icon>
            </template>
            {{ $t("page.knowledge.newCollection") }}
          </n-button>
        </div>
        <div v-if="papers.length" class="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <button
            v-for="entry in papers"
            :key="entry.id"
            type="button"
            class="knowledge-card"
            @click="openPaper(entry.id)"
          >
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div class="min-w-0">
                <div class="aira-type-meta">
                  {{ [entry.paper.first_author, entry.paper.publication_year, entry.paper.venue].filter(Boolean).join(" · ") || entry.source_type }}
                </div>
                <h2 class="aira-type-card-title line-clamp-2 mb-0 mt-1">
                  {{ entry.paper.title }}
                </h2>
              </div>
              <n-tag :type="entry.visibility === 'restricted' ? 'warning' : 'info'" round size="small">
                {{ visibilityLabel(entry.visibility) }}
              </n-tag>
            </div>
            <p v-if="entry.paper.abstract" class="aira-type-body aira-text-secondary line-clamp-3 mb-0 mt-3">
              {{ entry.paper.abstract }}
            </p>
            <div class="mt-4 flex flex-wrap items-center gap-2">
              <n-tag v-if="entry.paper.doi" size="small" round>
                DOI
              </n-tag>
              <n-tag v-for="tag in entry.tags.slice(0, 4)" :key="tag" size="small" round>
                {{ tag }}
              </n-tag>
              <span class="aira-type-meta ml-auto"><n-time :time="new Date(entry.created_at)" type="relative" /></span>
            </div>
          </button>
        </div>
        <n-empty v-else-if="!loading" class="knowledge-empty" :description="$t('page.knowledge.noPapers')">
          <template #extra>
            <import-paper-modal :scope="scope" :scope-label="scopeLabel" @imported="handlePaperImported" />
          </template>
        </n-empty>
      </template>

      <template v-else>
        <div v-if="knowledgeItems.length" class="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <article v-for="item in knowledgeItems" :key="item.id" class="knowledge-card">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div class="min-w-0">
                <div class="flex flex-wrap items-center gap-2">
                  <n-tag size="small" round>
                    {{ kindLabel(item.kind) }}
                  </n-tag>
                  <n-tag :type="stateType(item.state)" size="small" round>
                    {{ stateLabel(item.state) }}
                  </n-tag>
                  <span v-if="item.derived_from_id" class="aira-type-meta">{{ $t("page.knowledge.derived") }}</span>
                </div>
                <h2 class="aira-type-card-title mb-0 mt-2">
                  {{ item.title }}
                </h2>
              </div>
              <span class="aira-type-meta">{{ $t("page.knowledge.revision", { revision: item.revision }) }}</span>
            </div>
            <p class="aira-type-body aira-text-secondary line-clamp-5 mb-0 mt-3 whitespace-pre-wrap">
              {{ item.body }}
            </p>
            <div class="mt-4 flex flex-wrap items-center gap-2">
              <n-tag v-for="tag in item.tags" :key="tag" size="small" round>
                {{ tag }}
              </n-tag>
              <div class="ml-auto flex flex-wrap gap-2">
                <n-button size="small" secondary @click="editorRef?.open({ item })">
                  {{ $t("common.edit") }}
                </n-button>
                <n-button
                  v-if="item.scope_type !== 'personal' && ['draft', 'suggested'].includes(item.state)"
                  size="small"
                  type="primary"
                  ghost
                  @click="reviewItem(item)"
                >
                  {{ $t("page.knowledge.review") }}
                </n-button>
                <n-button
                  v-if="item.scope_type !== 'lab'"
                  size="small"
                  @click="openPublish(item)"
                >
                  {{ $t("page.knowledge.publish") }}
                </n-button>
              </div>
            </div>
          </article>
        </div>
        <n-empty v-else-if="!loading" class="knowledge-empty" :description="$t('page.knowledge.noItems')">
          <template #extra>
            <n-button type="primary" @click="editorRef?.open()">
              {{ $t("page.knowledge.newKnowledge") }}
            </n-button>
          </template>
        </n-empty>
      </template>
    </n-spin>

    <div v-if="hasNextPage" class="mt-6 flex justify-center">
      <n-button secondary :loading="loading" @click="loadMore">
        {{ $t("common.loadMore") }}
      </n-button>
    </div>

    <n-drawer v-model:show="paperDrawerVisible" :width="paperDrawerWidth" placement="right">
      <n-drawer-content :title="$t('page.knowledge.paperDetails')" closable>
        <n-spin :show="paperLoading">
          <template v-if="selectedPaper">
            <div class="flex flex-wrap items-center gap-2">
              <n-tag :type="selectedPaper.visibility === 'restricted' ? 'warning' : 'info'" round>
                {{ visibilityLabel(selectedPaper.visibility) }}
              </n-tag>
              <n-tag v-if="selectedPaper.files?.length" type="success" round>
                {{ $t("page.knowledge.fullTextAvailable") }}
              </n-tag>
            </div>
            <h2 class="aira-type-section-title mb-0 mt-4">
              {{ selectedPaper.paper.title }}
            </h2>
            <p class="aira-type-body aira-text-secondary mb-0 mt-2">
              {{ selectedPaper.paper.authors.join(", ") }}
            </p>
            <p class="aira-type-meta aira-text-muted mb-0 mt-1">
              {{ [selectedPaper.paper.venue, selectedPaper.paper.publication_year, selectedPaper.paper.doi].filter(Boolean).join(" · ") }}
            </p>
            <p v-if="selectedPaper.paper.abstract" class="aira-type-body aira-text-secondary mt-5 whitespace-pre-wrap">
              {{ selectedPaper.paper.abstract }}
            </p>

            <n-divider />
            <n-form label-placement="top">
              <n-form-item :label="$t('page.knowledge.notes')">
                <n-input
                  v-model:value="paperNotes"
                  type="textarea"
                  :autosize="{ minRows: 4, maxRows: 10 }"
                  :placeholder="$t('page.knowledge.notesPlaceholder')"
                />
              </n-form-item>
              <n-form-item :label="$t('page.knowledge.tags')">
                <n-dynamic-tags v-model:value="paperTags" />
              </n-form-item>
              <n-form-item :label="$t('page.knowledge.collections')">
                <n-select
                  v-model:value="paperCollectionIds"
                  multiple
                  clearable
                  :options="collectionOptions"
                  @update:value="updatePaperCollections"
                />
              </n-form-item>
              <n-button type="primary" :loading="paperSaving" @click="savePaperMetadata">
                {{ $t("page.knowledge.saveMetadata") }}
              </n-button>
            </n-form>

            <n-divider />
            <div class="flex flex-wrap gap-2">
              <n-button
                v-if="selectedPaper.files?.[0]"
                :loading="fileLoading"
                @click="openProtectedFile(selectedPaper.files[0], 'preview')"
              >
                {{ $t("page.knowledge.previewPdf") }}
              </n-button>
              <n-button
                v-if="selectedPaper.files?.[0]"
                :loading="fileLoading"
                @click="openProtectedFile(selectedPaper.files[0], 'download')"
              >
                {{ $t("page.knowledge.downloadPdf") }}
              </n-button>
              <n-button @click="downloadExport('bibtex')">
                {{ $t("page.knowledge.exportBibtex") }}
              </n-button>
              <n-button @click="downloadExport('ris')">
                {{ $t("page.knowledge.exportRis") }}
              </n-button>
              <n-button type="primary" ghost @click="createKnowledgeFromPaper">
                {{ $t("page.knowledge.createFromPaper") }}
              </n-button>
            </div>
          </template>
        </n-spin>
      </n-drawer-content>
    </n-drawer>

    <n-modal v-model:show="collectionModalVisible" preset="card" class="small-modal" :title="$t('page.knowledge.newCollection')">
      <n-form label-placement="top">
        <n-form-item :label="$t('page.knowledge.collectionName')" required>
          <n-input v-model:value="collectionForm.name" />
        </n-form-item>
        <n-form-item :label="$t('page.knowledge.collectionDescription')">
          <n-input v-model:value="collectionForm.description" type="textarea" />
        </n-form-item>
      </n-form>
      <template #footer>
        <div class="flex justify-end gap-2">
          <n-button @click="collectionModalVisible = false">
            {{ $t("common.cancel") }}
          </n-button>
          <n-button type="primary" :disabled="!collectionForm.name.trim()" :loading="collectionSaving" @click="saveCollection">
            {{ $t("common.create") }}
          </n-button>
        </div>
      </template>
    </n-modal>

    <n-modal v-model:show="publishModalVisible" preset="card" class="knowledge-modal" :title="$t('page.knowledge.publish')">
      <template v-if="publishingItem">
        <n-alert type="info" class="mb-4">
          {{ $t("page.knowledge.publishImpact") }}
        </n-alert>
        <n-form v-if="publishingItem.scope_type === 'personal' && !publishPreview" label-placement="top">
          <n-form-item :label="$t('page.knowledge.targetProject')" required>
            <n-select v-model:value="publishTargetProjectId" filterable :options="projectOptions" />
          </n-form-item>
        </n-form>
        <section v-if="publishPreview" class="knowledge-preview-card">
          <div class="aira-type-eyebrow">
            {{ $t("page.knowledge.importDestination") }}
          </div>
          <div class="aira-type-card-title mt-2">
            {{ publishTargetLabel }}
          </div>
          <p class="aira-type-body aira-text-secondary mb-0 mt-3">
            {{ $t("page.knowledge.filesOmitted", { count: publishPreview.impact.private_files_omitted.length }) }}
          </p>
        </section>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2">
          <n-button @click="publishPreview ? publishPreview = null : publishModalVisible = false">
            {{ publishPreview ? $t("page.knowledge.backToEdit") : $t("common.cancel") }}
          </n-button>
          <n-button v-if="!publishPreview" type="primary" :disabled="!canPreviewPublish" :loading="publishSaving" @click="previewPublish">
            {{ $t("page.knowledge.previewPublish") }}
          </n-button>
          <n-button v-else type="primary" :loading="publishSaving" @click="confirmPublish">
            {{ $t("page.knowledge.confirmPublish") }}
          </n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import type {
  KnowledgeItem,
  KnowledgeKind,
  KnowledgePublishPreview,
  KnowledgeScope,
  KnowledgeState,
  KnowledgeVisibility,
  PaperCollection,
  PaperLibraryEntry,
  ResearchFileSummary,
} from "@/service/api/knowledge"
import type { TagProps } from "naive-ui"
import {
  addPaperToCollection,
  confirmKnowledgePublish,
  createCollection,
  exportPaper,
  fetchCollections,
  fetchKnowledgeItems,
  fetchPaper,
  fetchPapers,
  fetchResearchFile,
  previewKnowledgePublish,
  removePaperFromCollection,
  reviewKnowledgeItem,
  updatePaperEntry,
} from "@/service/api/knowledge"
import { getLabInfoByUid } from "@/service/api/labs"
import { getProjectInfo } from "@/service/api/projects"
import { fetchUserProjects } from "@/service/api/users"
import { useAuthStore } from "@/store/modules/auth"
import { $t } from "@airalogy/shared/locales"
import { useRoute } from "vue-router"
import ImportPaperModal from "./components/import-paper-modal.vue"
import KnowledgeEditorModal from "./components/knowledge-editor-modal.vue"

interface KnowledgeEditorHandle {
  open: (options?: { item?: KnowledgeItem, paperId?: string, paperTitle?: string }) => void
}

const route = useRoute()
const authStore = useAuthStore()
const editorRef = ref<KnowledgeEditorHandle | null>(null)
const activeView = ref<"papers" | "items">("papers")
const loading = ref(false)
const contextsLoading = ref(false)
const loadError = ref(false)
const search = ref("")
const page = ref(1)
const pageSize = 20
const hasNextPage = ref(false)
const projects = ref<Api.Project.MyProjectInfo[]>([])
const selectedScopeKey = ref("personal")
const routeProject = ref<Api.Project.MyProjectInfo | null>(null)
const routeLab = ref<Api.Lab.LabInfo | null>(null)
const papers = ref<PaperLibraryEntry[]>([])
const knowledgeItems = ref<KnowledgeItem[]>([])
const collections = ref<PaperCollection[]>([])
const kindFilter = ref<KnowledgeKind | null>(null)
const stateFilter = ref<KnowledgeState | null>(null)

const paperDrawerVisible = ref(false)
const paperLoading = ref(false)
const paperSaving = ref(false)
const fileLoading = ref(false)
const selectedPaper = ref<PaperLibraryEntry | null>(null)
const paperNotes = ref("")
const paperTags = ref<string[]>([])
const paperCollectionIds = ref<string[]>([])

const collectionModalVisible = ref(false)
const collectionSaving = ref(false)
const collectionForm = reactive({ name: "", description: "" })

const publishModalVisible = ref(false)
const publishSaving = ref(false)
const publishingItem = ref<KnowledgeItem | null>(null)
const publishTargetProjectId = ref("")
const publishPreview = ref<KnowledgePublishPreview | null>(null)

const contextLocked = computed(() => route.name === "lab-knowledge" || route.name === "project-knowledge")
const availableLabs = computed(() => {
  const values = new Map<string, { id: string, uid: string, name: string }>()
  projects.value.forEach((project) => {
    values.set(String(project.lab_id), {
      id: String(project.lab_id),
      uid: project.lab_uid,
      name: project.lab_name || project.lab_uid,
    })
  })
  return [...values.values()]
})
const scopeOptions = computed(() => [
  { label: $t("page.knowledge.myKnowledge"), value: "personal" },
  ...availableLabs.value.map(lab => ({
    label: `${$t("page.knowledge.scopeLab")} · ${lab.name}`,
    value: `lab:${lab.id}`,
  })),
  ...projects.value.map(project => ({
    label: `${$t("page.knowledge.scopeProject")} · ${project.lab_name || project.lab_uid} / ${project.name}`,
    value: `project:${project.id}`,
  })),
])
const selectedProject = computed(() => {
  if (routeProject.value)
    return routeProject.value
  if (!selectedScopeKey.value.startsWith("project:"))
    return null
  return projects.value.find(project => String(project.id) === selectedScopeKey.value.slice(8)) || null
})
const selectedLab = computed(() => {
  if (routeLab.value)
    return { id: String(routeLab.value.id), uid: routeLab.value.uid, name: routeLab.value.name }
  if (selectedProject.value) {
    return {
      id: String(selectedProject.value.lab_id),
      uid: selectedProject.value.lab_uid,
      name: selectedProject.value.lab_name || selectedProject.value.lab_uid,
    }
  }
  if (!selectedScopeKey.value.startsWith("lab:"))
    return null
  return availableLabs.value.find(lab => lab.id === selectedScopeKey.value.slice(4)) || null
})
const scope = computed<KnowledgeScope>(() => {
  if (selectedProject.value) {
    return {
      scope_type: "project",
      lab_id: String(selectedProject.value.lab_id),
      project_id: String(selectedProject.value.id),
      visibility: "project",
    }
  }
  if (selectedLab.value) {
    return {
      scope_type: "lab",
      lab_id: selectedLab.value.id,
      visibility: "lab",
    }
  }
  return { scope_type: "personal", visibility: "private" }
})
const scopeLabel = computed(() => {
  if (selectedProject.value)
    return `${selectedProject.value.lab_name || selectedProject.value.lab_uid} / ${selectedProject.value.name}`
  if (selectedLab.value)
    return selectedLab.value.name
  return $t("page.knowledge.myKnowledge")
})
const pageTitle = computed(() => {
  if (scope.value.scope_type === "project")
    return $t("page.knowledge.projectKnowledge")
  if (scope.value.scope_type === "lab")
    return $t("page.knowledge.labKnowledge")
  return $t("page.knowledge.myKnowledge")
})
const kindOptions = computed(() => (["reference", "note", "method", "decision", "finding"] as KnowledgeKind[]).map(value => ({
  value,
  label: kindLabel(value),
})))
const stateOptions = computed(() => (["suggested", "draft", "reviewed", "superseded", "archived"] as KnowledgeState[]).map(value => ({
  value,
  label: stateLabel(value),
})))
const collectionOptions = computed(() => collections.value.map(item => ({ label: item.name, value: item.id })))
const projectOptions = computed(() => projects.value.map(project => ({
  label: `${project.lab_name || project.lab_uid} / ${project.name}`,
  value: String(project.id),
})))
const paperDrawerWidth = computed(() => Math.min(640, Math.max(320, window.innerWidth - 24)))
const canPreviewPublish = computed(() => {
  if (!publishingItem.value)
    return false
  return publishingItem.value.scope_type === "project" || Boolean(publishTargetProjectId.value)
})
const publishTargetLabel = computed(() => {
  if (publishingItem.value?.scope_type === "project")
    return selectedLab.value?.name || "Lab"
  const project = projects.value.find(item => String(item.id) === publishTargetProjectId.value)
  return project ? `${project.lab_name || project.lab_uid} / ${project.name}` : "Project"
})

async function loadContexts() {
  contextsLoading.value = true
  try {
    if (route.name === "project-knowledge") {
      const { labUid, projectUid } = route.params as Record<string, string>
      routeProject.value = await getProjectInfo({ labUid, projectUid })
      if (!routeProject.value)
        throw new Error("Project not found")
      selectedScopeKey.value = `project:${routeProject.value.id}`
      return
    }
    if (route.name === "lab-knowledge") {
      const { labUid } = route.params as Record<string, string>
      const response = await getLabInfoByUid(labUid)
      routeLab.value = response.data?.data || null
      if (!routeLab.value)
        throw new Error("Lab not found")
      selectedScopeKey.value = `lab:${routeLab.value.id}`
      return
    }
    const result = await fetchUserProjects(authStore.userInfo.id, {
      page: 1,
      pageSize: 100,
      sortedBy: "updated_at",
    })
    projects.value = result?.projects || []
  }
  finally {
    contextsLoading.value = false
  }
}

async function loadCollections() {
  const result = await fetchCollections(scope.value)
  collections.value = result.items
}

async function loadCurrentView(append = false) {
  loading.value = true
  loadError.value = false
  try {
    if (!append)
      page.value = 1
    if (activeView.value === "papers") {
      const result = await fetchPapers({
        ...scope.value,
        q: search.value.trim(),
        page: page.value,
        pageSize,
      })
      papers.value = append ? [...papers.value, ...result.items] : result.items
      hasNextPage.value = result.items.length === pageSize
      await loadCollections()
    }
    else {
      const result = await fetchKnowledgeItems({
        ...scope.value,
        q: search.value.trim(),
        kind: kindFilter.value || undefined,
        state: stateFilter.value || undefined,
        page: page.value,
        pageSize,
      })
      knowledgeItems.value = append ? [...knowledgeItems.value, ...result.items] : result.items
      hasNextPage.value = result.items.length === pageSize
    }
  }
  catch {
    loadError.value = true
  }
  finally {
    loading.value = false
  }
}

async function handleScopeChange() {
  selectedPaper.value = null
  await loadCurrentView()
}

async function loadMore() {
  page.value += 1
  await loadCurrentView(true)
}

async function openPaper(entryId: string) {
  paperDrawerVisible.value = true
  paperLoading.value = true
  try {
    selectedPaper.value = await fetchPaper(entryId)
    paperNotes.value = selectedPaper.value.notes || ""
    paperTags.value = [...selectedPaper.value.tags]
    paperCollectionIds.value = [...(selectedPaper.value.collection_ids || [])]
  }
  finally {
    paperLoading.value = false
  }
}

async function savePaperMetadata() {
  if (!selectedPaper.value)
    return
  paperSaving.value = true
  try {
    selectedPaper.value = await updatePaperEntry(selectedPaper.value.id, {
      notes: paperNotes.value,
      tags: paperTags.value,
    })
    window.$message?.success($t("page.knowledge.saved"))
    await loadCurrentView()
  }
  finally {
    paperSaving.value = false
  }
}

async function updatePaperCollections(nextIds: string[]) {
  if (!selectedPaper.value)
    return
  const previous = new Set(selectedPaper.value.collection_ids || [])
  const next = new Set(nextIds)
  await Promise.all([
    ...[...next].filter(id => !previous.has(id)).map(id => addPaperToCollection(id, selectedPaper.value!.id)),
    ...[...previous].filter(id => !next.has(id)).map(id => removePaperFromCollection(id, selectedPaper.value!.id)),
  ])
  selectedPaper.value.collection_ids = nextIds
}

function saveBlob(blob: Blob, filename: string, open = false) {
  const url = URL.createObjectURL(blob)
  if (open) {
    window.open(url, "_blank", "noopener,noreferrer")
  }
  else {
    const anchor = document.createElement("a")
    anchor.href = url
    anchor.download = filename
    anchor.click()
  }
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
}

async function openProtectedFile(file: ResearchFileSummary, mode: "preview" | "download") {
  fileLoading.value = true
  try {
    const blob = await fetchResearchFile(file.id, mode)
    saveBlob(blob, file.filename, mode === "preview")
  }
  catch {
    window.$message?.error($t("page.knowledge.fileOpenError"))
  }
  finally {
    fileLoading.value = false
  }
}

async function downloadExport(format: "bibtex" | "ris") {
  if (!selectedPaper.value)
    return
  const blob = await exportPaper(selectedPaper.value.id, format)
  if (blob)
    saveBlob(blob, `paper.${format === "bibtex" ? "bib" : "ris"}`)
}

function createKnowledgeFromPaper() {
  if (!selectedPaper.value)
    return
  paperDrawerVisible.value = false
  editorRef.value?.open({
    paperId: selectedPaper.value.id,
    paperTitle: selectedPaper.value.paper.title,
  })
}

async function saveCollection() {
  if (!collectionForm.name.trim())
    return
  collectionSaving.value = true
  try {
    await createCollection({
      ...scope.value,
      name: collectionForm.name.trim(),
      description: collectionForm.description.trim(),
    })
    window.$message?.success($t("page.knowledge.collectionCreated"))
    collectionModalVisible.value = false
    Object.assign(collectionForm, { name: "", description: "" })
    await loadCollections()
  }
  finally {
    collectionSaving.value = false
  }
}

function reviewItem(item: KnowledgeItem) {
  window.$dialog?.warning({
    title: $t("page.knowledge.review"),
    content: $t("page.knowledge.reviewHint"),
    positiveText: $t("page.knowledge.review"),
    negativeText: $t("common.cancel"),
    async onPositiveClick() {
      await reviewKnowledgeItem(item.id, item.revision)
      window.$message?.success($t("page.knowledge.reviewed"))
      await loadCurrentView()
    },
  })
}

function openPublish(item: KnowledgeItem) {
  publishingItem.value = item
  publishPreview.value = null
  publishTargetProjectId.value = projects.value.length === 1 ? String(projects.value[0].id) : ""
  publishModalVisible.value = true
}

function publishPayload() {
  if (!publishingItem.value)
    throw new Error("No Knowledge item selected")
  if (publishingItem.value.scope_type === "project") {
    return {
      target_scope_type: "lab" as const,
      target_lab_id: publishingItem.value.lab_id || undefined,
    }
  }
  const project = projects.value.find(item => String(item.id) === publishTargetProjectId.value)
  if (!project)
    throw new Error("Target Project is required")
  return {
    target_scope_type: "project" as const,
    target_lab_id: String(project.lab_id),
    target_project_id: String(project.id),
  }
}

async function previewPublish() {
  if (!publishingItem.value)
    return
  publishSaving.value = true
  try {
    publishPreview.value = await previewKnowledgePublish(publishingItem.value.id, publishPayload())
  }
  finally {
    publishSaving.value = false
  }
}

async function confirmPublish() {
  if (!publishingItem.value || !publishPreview.value)
    return
  publishSaving.value = true
  try {
    await confirmKnowledgePublish(publishingItem.value.id, {
      ...publishPayload(),
      expected_revision: publishingItem.value.revision,
      preview_digest: publishPreview.value.preview_digest,
    })
    window.$message?.success($t("page.knowledge.published"))
    publishModalVisible.value = false
    await loadCurrentView()
  }
  finally {
    publishSaving.value = false
  }
}

function handlePaperImported(entry: PaperLibraryEntry) {
  activeView.value = "papers"
  void loadCurrentView().then(() => openPaper(entry.id))
}

function handleKnowledgeSaved() {
  activeView.value = "items"
  void loadCurrentView()
}

function visibilityLabel(value: KnowledgeVisibility) {
  const key = value === "private"
    ? "visibilityPrivate"
    : value === "lab"
      ? "visibilityLab"
      : value === "project"
        ? "visibilityProject"
        : "visibilityRestricted"
  return $t(`page.knowledge.${key}` as I18n.I18nKey)
}

function kindLabel(value: KnowledgeKind) {
  const suffix = value.charAt(0).toUpperCase() + value.slice(1)
  return $t(`page.knowledge.kind${suffix}` as I18n.I18nKey)
}

function stateLabel(value: KnowledgeState) {
  const suffix = value.charAt(0).toUpperCase() + value.slice(1)
  return $t(`page.knowledge.state${suffix}` as I18n.I18nKey)
}

function stateType(value: KnowledgeState): TagProps["type"] {
  if (value === "reviewed")
    return "success"
  if (value === "suggested")
    return "info"
  if (value === "superseded" || value === "archived")
    return "default"
  return "warning"
}

watch(() => route.fullPath, async () => {
  routeProject.value = null
  routeLab.value = null
  await loadContexts()
  await loadCurrentView()
})

onMounted(async () => {
  try {
    await loadContexts()
    if (contextLocked.value && !projects.value.length && authStore.userInfo.id) {
      const result = await fetchUserProjects(authStore.userInfo.id, { page: 1, pageSize: 100, sortedBy: "updated_at" })
      projects.value = result?.projects || []
    }
    await loadCurrentView()
  }
  catch {
    loadError.value = true
  }
})
</script>

<style scoped>
.knowledge-page {
  width: 100%;
}

.knowledge-hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1.5rem;
  border: 1px solid rgb(209 250 229);
  border-radius: 1rem;
  background: linear-gradient(135deg, rgb(16 185 129 / 8%), white 68%);
  padding: clamp(1.25rem, 3vw, 2rem);
}

.knowledge-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
}

.knowledge-scope-label {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  border: 1px solid rgb(229 231 235);
  border-radius: 0.5rem;
  background: white;
  padding: 0.5rem 0.75rem;
  color: rgb(75 85 99);
}

.knowledge-card {
  display: block;
  width: 100%;
  border: 1px solid rgb(229 231 235);
  border-radius: 0.875rem;
  background: white;
  padding: 1.25rem;
  text-align: left;
  transition: border-color 160ms ease, box-shadow 160ms ease, transform 160ms ease;
}

button.knowledge-card:hover,
button.knowledge-card:focus-visible {
  border-color: rgb(16 185 129 / 45%);
  box-shadow: 0 10px 28px rgb(15 23 42 / 8%);
  outline: none;
  transform: translateY(-1px);
}

.knowledge-empty {
  min-height: 18rem;
  display: flex;
  align-items: center;
  justify-content: center;
}

.knowledge-modal {
  width: min(42rem, calc(100vw - 2rem));
}

.small-modal {
  width: min(32rem, calc(100vw - 2rem));
}

.knowledge-preview-card {
  border: 1px solid rgb(229 231 235);
  border-radius: 0.75rem;
  background: rgb(249 250 251);
  padding: 1rem;
}

@media (max-width: 48rem) {
  .knowledge-hero {
    flex-direction: column;
  }
}
</style>

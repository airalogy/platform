<template>
  <div class="research-detail py-8">
    <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
      <n-button quaternary @click="goBack">
        <template #icon>
          <n-icon><icon-tabler-arrow-left /></n-icon>
        </template>
        {{ $t("page.research.backToTasks") }}
      </n-button>
      <n-button quaternary :loading="loading" @click="() => loadTask()">
        <template #icon>
          <n-icon><icon-tabler-refresh /></n-icon>
        </template>
        {{ $t("page.research.refresh") }}
      </n-button>
    </div>

    <n-alert v-if="loadError" type="error" :title="$t('page.research.loadError')">
      <n-button size="small" class="mt-2" @click="() => loadTask()">
        {{ $t("common.retry") }}
      </n-button>
    </n-alert>

    <n-spin v-else :show="loading && !task" class="min-h-80">
      <template v-if="task">
        <header class="research-detail__hero">
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-2">
              <span class="aira-type-meta">{{ task.lab.name }} / {{ task.project.name }}</span>
              <n-tag :type="taskStatusType" round size="small">
                {{ taskStatusLabel(task.status) }}
              </n-tag>
              <n-tag v-if="task.ai_available" type="info" round size="small">
                {{ $t("page.research.airaManaged") }}
              </n-tag>
            </div>
            <h1 class="aira-type-page-title mb-0 mt-2">
              {{ task.title }}
            </h1>
            <p class="aira-type-body aira-text-secondary mb-0 mt-3 whitespace-pre-wrap">
              {{ task.goal }}
            </p>
          </div>
          <div class="flex shrink-0 flex-wrap items-center gap-2">
            <n-button v-if="task.status === 'draft'" type="primary" :loading="mutating" @click="startTask">
              {{ task.ai_available && hasAiraCapabilities ? $t("page.research.startWithAira") : $t("page.research.startTask") }}
            </n-button>
            <n-button v-if="canAddAction" secondary @click="openActionModal">
              {{ $t("page.research.addProtocolWork") }}
            </n-button>
            <research-human-work-action-modal
              v-if="canAddAction"
              :task-id="task.id"
              :project-id="task.project_id"
              :owner="task.owner"
              @created="() => loadTask(true)"
            />
            <research-digital-action-modal
              v-if="canAddDigitalAction"
              :task-id="task.id"
              @created="() => loadTask(true)"
            />
            <research-resource-action-modal
              v-if="canAddDigitalAction && task.resources.length"
              :task-id="task.id"
              :lab-id="task.lab_id"
              :requirements="task.resources"
              @created="() => loadTask(true)"
            />
            <research-service-action-modal
              v-if="canAddServiceAction"
              :task-id="task.id"
              :services="task.services"
              @created="() => loadTask(true)"
            />
            <research-compute-action-modal
              v-if="canAddComputeAction"
              :task-id="task.id"
              :has-environments="task.compute.some(item => item.available)"
              @created="() => loadTask(true)"
            />
            <n-button v-if="task.status === 'active'" :loading="mutating" @click="pauseTask">
              {{ $t("page.research.pause") }}
            </n-button>
            <n-button v-if="task.status === 'paused' || task.status === 'failed'" type="primary" :loading="mutating" @click="resumeTask">
              {{ $t("page.research.resume") }}
            </n-button>
            <n-button v-if="canReview" type="primary" :loading="mutating" @click="openReviewModal">
              {{ $t("page.research.reviewResult") }}
            </n-button>
            <create-research-run-modal
              v-if="canCreateRun"
              :task-id="task.id"
              :task-revision="task.revision"
              :runs="task.runs"
              @created="() => loadTask(true)"
            />
            <n-button v-if="canCancel" type="error" tertiary :loading="mutating" @click="cancelTask">
              {{ $t("page.research.cancelTask") }}
            </n-button>
          </div>
        </header>

        <n-alert
          v-if="latestRun?.last_error"
          :type="latestRun.status === 'failed' ? 'error' : 'info'"
          class="mt-5"
          :title="$t('page.research.runNotice')"
        >
          {{ latestRun.last_error }}
        </n-alert>
        <n-alert v-if="task.status === 'review_required'" type="warning" class="mt-5">
          {{ $t("page.research.reviewRequiredHint") }}
        </n-alert>

        <div class="grid grid-cols-1 mt-6 gap-5 xl:grid-cols-[minmax(0,2fr)_minmax(280px,1fr)]">
          <div class="space-y-5">
            <section class="research-panel">
              <div class="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div class="aira-type-eyebrow">
                    {{ $t("page.research.currentRun") }}
                  </div>
                  <h2 class="aira-type-section-title mb-0 mt-1">
                    {{ latestRun ? $t("page.research.runNumber", { number: latestRun.run_number }) : "—" }}
                  </h2>
                </div>
                <n-tag v-if="latestRun" :type="runStatusType(latestRun.status)" round>
                  {{ runStatusLabel(latestRun.status) }}
                </n-tag>
              </div>
              <div v-if="latestRun" class="grid grid-cols-1 mt-4 gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <div class="research-metric">
                  <span class="aira-type-meta">{{ $t("page.research.planVersion") }}</span>
                  <strong class="aira-type-metric">v{{ latestRun.plan_version }}</strong>
                </div>
                <div class="research-metric">
                  <span class="aira-type-meta">{{ $t("page.research.openWork") }}</span>
                  <strong class="aira-type-metric">{{ task.open_work_items }}</strong>
                </div>
                <div class="research-metric">
                  <span class="aira-type-meta">{{ $t("page.research.pendingApprovals") }}</span>
                  <strong class="aira-type-metric">{{ task.pending_approvals }}</strong>
                </div>
                <div class="research-metric">
                  <span class="aira-type-meta">{{ $t("page.research.airaStage") }}</span>
                  <strong class="aira-type-label break-words">{{ airaStage }}</strong>
                </div>
              </div>
            </section>

            <section v-if="task.runs.length > 1" class="research-panel">
              <div class="aira-type-eyebrow">
                {{ $t("page.research.runHistory") }}
              </div>
              <h2 class="aira-type-section-title mb-0 mt-1">
                {{ $t("page.research.runComparison") }}
              </h2>
              <div class="mt-4 space-y-3">
                <article v-for="run in task.runs" :key="run.id" class="research-run-card">
                  <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div class="min-w-0 flex-1">
                      <div class="flex flex-wrap items-center gap-2">
                        <strong class="aira-type-label">
                          {{ $t("page.research.runNumber", { number: run.run_number }) }}
                        </strong>
                        <n-tag size="small" round>
                          {{ runKindLabel(run) }}
                        </n-tag>
                        <n-tag :type="runStatusType(run.status)" size="small" round>
                          {{ runStatusLabel(run.status) }}
                        </n-tag>
                      </div>
                      <p v-if="runOrigin(run)" class="aira-type-meta mb-0 mt-2">
                        {{ $t("page.research.inheritedFromRun", { number: runOrigin(run)?.source_run_number }) }}
                        <template v-if="runOrigin(run)?.purpose">
                          · {{ runOrigin(run)?.purpose }}
                        </template>
                      </p>
                      <p class="aira-type-body aira-text-secondary mb-0 mt-3 whitespace-pre-wrap">
                        {{ runConclusion(run) || $t("page.research.noRunConclusion") }}
                      </p>
                      <div class="mt-3 flex flex-wrap gap-2">
                        <n-tag v-if="run.result_package.goal_assessment" size="small" type="info">
                          {{ outcomeLabel(run.result_package.goal_assessment) }}
                        </n-tag>
                        <n-tag v-if="run.result_package.scientific_outcome" size="small" type="success">
                          {{ scientificOutcomeLabel(run.result_package.scientific_outcome) }}
                        </n-tag>
                      </div>
                    </div>
                    <time class="aira-type-meta shrink-0" :datetime="run.created_at">
                      {{ formatDateTime(run.created_at) }}
                    </time>
                  </div>
                </article>
              </div>
            </section>

            <section v-if="pendingApprovalActions.length" class="research-panel research-panel--attention">
              <div class="aira-type-eyebrow">
                {{ $t("page.research.approvalGate") }}
              </div>
              <h2 class="aira-type-section-title mb-0 mt-1">
                {{ $t("page.research.approvalRequired") }}
              </h2>
              <div class="mt-4 space-y-3">
                <article v-for="action in pendingApprovalActions" :key="action.id" class="research-action-card">
                  <div class="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                    <div class="min-w-0 flex-1">
                      <div class="flex flex-wrap items-center gap-2">
                        <n-tag type="warning" round size="small">
                          {{ $t("page.research.approvalPending") }}
                        </n-tag>
                        <span class="aira-type-meta">#{{ action.sequence }}</span>
                        <n-tag v-if="action.input_data.parallel_group" type="info" round size="small">
                          {{ $t("page.research.parallelBranch", {
                            position: action.input_data.parallel_group.position,
                            size: action.input_data.parallel_group.size,
                          }) }}
                        </n-tag>
                        <n-tag v-if="action.input_data.action_graph" type="info" round size="small">
                          {{ $t("page.research.dependencyNode", {
                            position: action.input_data.action_graph.position,
                            size: action.input_data.action_graph.size,
                          }) }}
                        </n-tag>
                        <span v-if="action.protocol" class="aira-type-meta">
                          {{ action.protocol.name }} · v{{ action.protocol.version }}
                        </span>
                      </div>
                      <h3 class="aira-type-card-title mb-0 mt-2">
                        {{ action.title }}
                      </h3>
                      <p class="aira-type-body aira-text-secondary mb-0 mt-2 whitespace-pre-wrap">
                        {{ action.description || action.approval?.reason }}
                      </p>
                      <research-action-impact :action="action" />
                      <div class="aira-type-meta mt-3 break-all">
                        {{ $t("page.research.previewDigest") }} · {{ action.preview_digest }}
                      </div>
                    </div>
                    <research-approval-actions
                      v-if="action.approval"
                      :approval="action.approval"
                      :action-revision="action.revision"
                      @decided="() => loadTask(true)"
                    />
                  </div>
                </article>
              </div>
            </section>

            <section v-if="openActions.length" class="research-panel">
              <div class="aira-type-eyebrow">
                {{ $t("page.research.needsAction") }}
              </div>
              <h2 class="aira-type-section-title mb-0 mt-1">
                {{ $t("page.research.humanWork") }}
              </h2>
              <div class="mt-4 space-y-3">
                <article v-for="action in openActions" :key="action.id" class="research-action-card">
                  <div class="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                    <div class="min-w-0 flex-1">
                      <div class="flex flex-wrap items-center gap-2">
                        <n-tag type="info" round size="small">
                          {{ actionStatusLabel(action.status) }}
                        </n-tag>
                        <span class="aira-type-meta">#{{ action.sequence }}</span>
                      </div>
                      <h3 class="aira-type-card-title mb-0 mt-2">
                        {{ action.title }}
                      </h3>
                      <p class="aira-type-body aira-text-secondary mb-0 mt-2 whitespace-pre-wrap">
                        {{ action.work_item?.instructions || action.description }}
                      </p>
                      <div class="aira-type-meta mt-3">
                        {{ $t("page.research.assignedTo") }} · {{ action.assignee?.name || action.assignee?.username }}
                      </div>
                    </div>
                    <n-button
                      v-if="canExecuteAction(action)"
                      type="primary"
                      :loading="startingWorkItemId === action.work_item?.id"
                      @click="executeWorkItem(action)"
                    >
                      {{ actionWorkLabel(action) }}
                    </n-button>
                  </div>
                </article>
              </div>
            </section>

            <section class="research-panel">
              <div class="aira-type-eyebrow">
                {{ $t("page.research.executionHistory") }}
              </div>
              <h2 class="aira-type-section-title mb-0 mt-1">
                {{ $t("page.research.actions") }}
              </h2>
              <n-empty v-if="!task.actions.length" class="py-8" :description="$t('page.research.noActions')" />
              <div v-else class="mt-4 divide-y divide-gray-100">
                <div v-for="action in task.actions" :key="action.id" class="flex gap-3 py-4 first:pt-0 last:pb-0">
                  <div class="research-sequence">
                    {{ action.sequence }}
                  </div>
                  <div class="min-w-0 flex-1">
                    <div class="flex flex-wrap items-center justify-between gap-2">
                      <h3 class="aira-type-label mb-0">
                        {{ action.title }}
                      </h3>
                      <div class="flex flex-wrap items-center justify-end gap-2">
                        <n-tag v-if="action.input_data.parallel_group" type="info" size="small" round>
                          {{ $t("page.research.parallelBranch", {
                            position: action.input_data.parallel_group.position,
                            size: action.input_data.parallel_group.size,
                          }) }}
                        </n-tag>
                        <n-tag v-if="action.input_data.action_graph" type="info" size="small" round>
                          {{ $t("page.research.dependencyNode", {
                            position: action.input_data.action_graph.position,
                            size: action.input_data.action_graph.size,
                          }) }}
                        </n-tag>
                        <n-tag :type="actionStatusType(action.status)" size="small" round>
                          {{ actionStatusLabel(action.status) }}
                        </n-tag>
                      </div>
                    </div>
                    <p v-if="action.description" class="aira-type-meta line-clamp-2 mb-0 mt-1">
                      {{ action.description }}
                    </p>
                    <p v-if="action.dependencies.length" class="aira-type-meta mb-0 mt-1">
                      {{ $t("page.research.dependsOn", { actions: actionDependencyLabel(action) }) }}
                    </p>
                    <p
                      v-if="action.input_data.action_graph?.result_bindings?.length"
                      class="aira-type-meta mb-0 mt-1"
                    >
                      {{ $t("page.research.dataBindings", {
                        count: action.input_data.action_graph.result_bindings.length,
                      }) }}
                    </p>
                    <n-button
                      v-if="action.protocol_run?.record_id && action.protocol"
                      text
                      type="primary"
                      class="mt-2"
                      @click="openRecord(action)"
                    >
                      {{ $t("page.research.viewEvidenceRecord") }}
                    </n-button>
                    <div v-if="action.tool_job" class="research-digital-result mt-3">
                      <div class="flex flex-wrap items-center justify-between gap-2">
                        <span class="aira-type-meta">
                          {{ $t("page.research.researchTool") }} · {{ action.tool_job.tool_key }} · v{{ action.tool_job.tool_version }}
                        </span>
                        <span class="aira-type-meta">
                          {{ $t("page.research.resultCount", { count: toolResultItems(action).length }) }}
                        </span>
                      </div>
                      <n-alert v-if="action.tool_job.error" type="error" class="mt-2">
                        {{ action.tool_job.error }}
                      </n-alert>
                      <div v-if="toolResultItems(action).length" class="mt-2 space-y-2">
                        <div
                          v-for="(item, index) in toolResultItems(action).slice(0, 3)"
                          :key="String(item.id || item.doi || index)"
                          class="research-tool-result"
                        >
                          <strong class="aira-type-label">{{ item.title || item.name || $t("page.research.unnamedResult") }}</strong>
                          <p v-if="item.body || item.abstract" class="aira-type-meta line-clamp-2 mb-0 mt-1">
                            {{ item.body || item.abstract }}
                          </p>
                        </div>
                      </div>
                    </div>
                    <div v-if="action.instrument_job" class="research-digital-result mt-3">
                      <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                        <div class="min-w-0">
                          <div class="flex flex-wrap items-center gap-2">
                            <span class="aira-type-label">
                              {{ $t("page.research.instrumentCommand") }} · {{ action.instrument_job.command_key }} · v{{ action.instrument_job.command_version }}
                            </span>
                            <n-tag size="small" round>
                              {{ instrumentJobStatusLabel(action.instrument_job.status) }}
                            </n-tag>
                            <n-tag :type="instrumentRiskType(action.instrument_job.risk)" size="small" round>
                              {{ $t(`page.resourceLibrary.risk.${action.instrument_job.risk}` as I18n.I18nKey) }}
                            </n-tag>
                          </div>
                          <div class="aira-type-meta mt-1">
                            {{ $t("page.research.instrumentAttempt", { count: action.instrument_job.attempt_count }) }}
                            · {{ $t("page.research.resourceRevision", { revision: action.instrument_job.resource_revision }) }}
                          </div>
                          <div v-if="action.instrument_job.heartbeat_at" class="aira-type-meta mt-1">
                            {{ $t("page.research.lastGatewayHeartbeat") }} · {{ formatDateTime(action.instrument_job.heartbeat_at) }}
                          </div>
                          <details class="mt-2">
                            <summary class="aira-type-meta cursor-pointer">
                              {{ $t("page.resourceLibrary.safetyContract") }}
                            </summary>
                            <pre class="mt-2">{{ formatPayload(action.instrument_job.safety_contract || {}) }}</pre>
                          </details>
                          <details v-if="Object.keys(action.instrument_job.safety_attestation || {}).length" class="mt-2">
                            <summary class="aira-type-meta cursor-pointer">
                              {{ $t("page.research.safetyAttestation") }}
                            </summary>
                            <pre class="mt-2">{{ formatPayload(action.instrument_job.safety_attestation) }}</pre>
                          </details>
                        </div>
                        <research-instrument-stop
                          :job="action.instrument_job"
                          @stopped="() => loadTask(true)"
                        />
                      </div>
                      <n-alert v-if="action.instrument_job.error || action.instrument_job.stop_reason" type="error" class="mt-2">
                        {{ action.instrument_job.error || action.instrument_job.stop_reason }}
                      </n-alert>
                      <pre v-if="Object.keys(action.instrument_job.result || {}).length" class="mt-3">{{ formatPayload(action.instrument_job.result) }}</pre>
                    </div>
                    <div v-if="action.compute_job" class="research-digital-result mt-3">
                      <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                        <div class="min-w-0">
                          <div class="flex flex-wrap items-center gap-2">
                            <span class="aira-type-label">
                              {{ $t("page.research.computeJob") }} · {{ action.compute_job.environment_snapshot.name || action.compute_job.compute_environment_id }} · r{{ action.compute_job.compute_environment_revision }}
                            </span>
                            <n-tag size="small" round>
                              {{ computeJobStatusLabel(action.compute_job.status) }}
                            </n-tag>
                            <n-tag size="small" round>
                              {{ action.compute_job.language === "python" ? "Python" : "R" }}
                            </n-tag>
                          </div>
                          <div class="aira-type-meta mt-1">
                            {{ $t("page.research.computeAttempt", { count: action.compute_job.attempt_count }) }}
                            <template v-if="action.compute_job.actual_cost || action.compute_job.estimated_cost">
                              · {{ action.compute_job.actual_cost || action.compute_job.estimated_cost }} {{ action.compute_job.currency }}
                            </template>
                          </div>
                          <div v-if="action.compute_job.heartbeat_at" class="aira-type-meta mt-1">
                            {{ $t("page.research.lastRunnerHeartbeat") }} · {{ formatDateTime(action.compute_job.heartbeat_at) }}
                          </div>
                          <div class="aira-type-meta mt-1 break-all">
                            {{ $t("page.research.computeSourceDigest") }} · {{ action.compute_job.source_sha256 }}
                          </div>
                        </div>
                        <research-compute-job-actions
                          :job="action.compute_job"
                          @changed="() => loadTask(true)"
                        />
                      </div>
                      <n-alert v-if="action.compute_job.error || action.compute_job.cancel_reason" type="error" class="mt-2">
                        {{ action.compute_job.error || action.compute_job.cancel_reason }}
                      </n-alert>
                      <div v-if="Object.keys(action.compute_job.result || {}).length" class="mt-3">
                        <div class="aira-type-meta">
                          {{ $t("page.research.computeResult") }}
                        </div>
                        <pre>{{ formatPayload(action.compute_job.result) }}</pre>
                      </div>
                      <div v-if="action.compute_job.output_manifest?.length" class="mt-3">
                        <div class="aira-type-meta">
                          {{ $t("page.research.computeOutputs") }}
                        </div>
                        <div class="grid grid-cols-1 mt-2 gap-2 lg:grid-cols-2">
                          <div
                            v-for="output in action.compute_job.output_manifest"
                            :key="output.id"
                            class="research-method"
                          >
                            <div class="flex flex-wrap items-start justify-between gap-2">
                              <div class="min-w-0">
                                <div class="aira-type-label truncate">
                                  {{ output.asset_name }}
                                </div>
                                <div class="aira-type-meta mt-1 break-all">
                                  {{ output.mount_name }} · {{ output.media_type }}
                                </div>
                              </div>
                              <n-tag
                                size="small"
                                round
                                :type="output.status === 'registered' ? 'success' : output.status === 'uploaded' ? 'info' : 'default'"
                              >
                                {{ computeOutputStatusLabel(output.status) }}
                              </n-tag>
                            </div>
                            <div class="aira-type-meta mt-2">
                              {{ output.byte_size == null ? $t("page.research.computeOutputLimit", { size: formatFileSize(output.max_bytes) }) : formatFileSize(output.byte_size) }}
                              <template v-if="output.required">
                                · {{ $t("page.research.computeOutputRequired") }}
                              </template>
                            </div>
                            <div v-if="output.status === 'registered'" class="aira-type-meta mt-1">
                              {{ $t("page.research.computeOutputDraftHint") }}
                            </div>
                          </div>
                        </div>
                      </div>
                      <div v-if="Object.keys(action.compute_job.usage || {}).length" class="mt-3">
                        <div class="aira-type-meta">
                          {{ $t("page.research.computeUsage") }}
                        </div>
                        <pre>{{ formatPayload(action.compute_job.usage) }}</pre>
                      </div>
                    </div>
                    <research-service-job-actions
                      v-if="action.service_job"
                      class="mt-3"
                      :job="action.service_job"
                      :task-id="task.id"
                      :lab-id="task.lab_id"
                      :can-manage="task.permissions.can_manage_services"
                      @changed="() => loadTask(true)"
                    />
                    <div v-if="action.wait_event" class="research-digital-result mt-3">
                      <div class="flex flex-wrap items-start justify-between gap-3">
                        <div class="min-w-0">
                          <div class="aira-type-label">
                            {{ $t("page.research.expectedEvent") }} · {{ action.wait_event.expected_event_type }}
                          </div>
                          <div class="aira-type-meta mt-1 break-all">
                            {{ $t("page.research.eventKey") }} · {{ action.wait_event.event_key }}
                          </div>
                        </div>
                        <research-wait-event-signal
                          v-if="action.wait_event.status === 'waiting' && action.status === 'waiting'"
                          :event="action.wait_event"
                          @signaled="() => loadTask(true)"
                        />
                      </div>
                      <pre v-if="action.wait_event.status === 'received'">{{ formatPayload(action.wait_event.received_payload) }}</pre>
                    </div>
                    <div v-if="action.resource_reservation" class="research-digital-result mt-3">
                      <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                        <div class="min-w-0">
                          <div class="flex flex-wrap items-center gap-2">
                            <span class="aira-type-label">
                              {{ resourceKindLabel(action.resource_reservation.kind) }}
                            </span>
                            <n-tag size="small" round>
                              {{ action.resource_reservation.status.replaceAll("_", " ") }}
                            </n-tag>
                          </div>
                          <div v-if="action.resource_reservation.kind === 'inventory'" class="aira-type-meta mt-1">
                            {{ action.resource_reservation.quantity }} {{ action.resource_reservation.unit }}
                          </div>
                          <div v-else class="aira-type-meta mt-1">
                            {{ formatDateTime(action.resource_reservation.starts_at) }} – {{ formatDateTime(action.resource_reservation.ends_at) }}
                          </div>
                          <div
                            v-if="action.resource_reservation.consumptions?.length"
                            class="mt-3 space-y-2"
                          >
                            <div class="aira-type-label">
                              {{ $t("page.research.inventoryConsumptionHistory") }}
                            </div>
                            <button
                              v-for="consumption in action.resource_reservation.consumptions"
                              :key="consumption.id"
                              type="button"
                              class="research-consumption"
                              @click="openResourceConsumptionRecord(consumption)"
                            >
                              <span class="aira-type-body">
                                {{ $t("page.research.consumptionRecord", {
                                  number: consumption.record_number,
                                  version: consumption.record_version,
                                }) }}
                              </span>
                              <span class="aira-type-meta">
                                {{ $t("page.research.consumedAmount", {
                                  quantity: consumption.quantity,
                                  unit: consumption.unit,
                                }) }}
                                ·
                                {{ $t("page.research.remainingAmount", {
                                  quantity: consumption.remaining_quantity,
                                  unit: consumption.remaining_unit,
                                }) }}
                              </span>
                            </button>
                          </div>
                        </div>
                        <research-resource-reservation-actions
                          :reservation="action.resource_reservation"
                          @changed="() => loadTask(true)"
                        />
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </section>

            <research-assets-panel
              :task-id="task.id"
              :lab-uid="task.lab.uid"
              :project-uid="task.project.uid"
              :protocols="task.protocols"
              :actions="task.actions"
              @changed="() => loadTask(true)"
            />

            <research-result-package-panel
              :task-id="task.id"
              :outcome="task.outcome"
              :scientific-outcome="task.scientific_outcome"
              :conclusion="resultConclusion"
              :result-package="task.result_package"
            />
          </div>

          <aside class="space-y-5">
            <research-budget-panel
              :task-id="task.id"
              :task-revision="task.revision"
              :deadline-at="task.deadline_at"
              :budget-limit="task.budget_limit"
              :budget-currency="task.budget_currency"
              :can-manage="canManageBudget"
              :can-amend="canAmendLimits"
              @changed="() => loadTask(true)"
            />
            <section class="research-panel">
              <div class="aira-type-eyebrow">
                {{ $t("page.research.definitionOfDone") }}
              </div>
              <h2 class="aira-type-card-title mb-0 mt-1">
                {{ $t("page.research.successCriteria") }}
              </h2>
              <ul class="aira-type-body aira-text-secondary mb-0 mt-3 pl-5 space-y-2">
                <li v-for="criterion in task.success_criteria" :key="criterion">
                  {{ criterion }}
                </li>
              </ul>
              <template v-if="task.stop_conditions.length">
                <n-divider />
                <h3 class="aira-type-label mb-0">
                  {{ $t("page.research.stopConditions") }}
                </h3>
                <ul class="aira-type-meta mb-0 mt-2 pl-5 space-y-1">
                  <li v-for="condition in task.stop_conditions" :key="condition">
                    {{ condition }}
                  </li>
                </ul>
              </template>
            </section>

            <section class="research-panel">
              <div class="aira-type-eyebrow">
                {{ $t("page.research.researchEnvironment") }}
              </div>
              <h2 class="aira-type-card-title mb-0 mt-1">
                {{ $t("page.research.pinnedMethods") }}
              </h2>
              <div v-if="task.protocols.length" class="mt-3 space-y-2">
                <button
                  v-for="protocol in task.protocols"
                  :key="`${protocol.id}:${protocol.version}`"
                  type="button"
                  class="research-method"
                  @click="openProtocol(protocol)"
                >
                  <span class="aira-type-label">{{ protocol.position }}. {{ protocol.name }}</span>
                  <span class="aira-type-meta">v{{ protocol.version }}</span>
                </button>
              </div>
              <n-empty v-else class="py-5" :description="$t('page.research.noMethods')" />
              <n-divider />
              <h2 class="aira-type-card-title mb-0">
                {{ $t("page.research.pinnedDigitalCapabilities") }}
              </h2>
              <div v-if="pinnedTools.length" class="mt-3 space-y-2">
                <div v-for="tool in pinnedTools" :key="`${tool.key}:${tool.version}`" class="research-method">
                  <span class="aira-type-label">{{ tool.name }}</span>
                  <span class="aira-type-meta">v{{ tool.version }}</span>
                </div>
              </div>
              <p v-else class="aira-type-meta aira-text-muted mb-0 mt-3">
                {{ $t("page.research.noDigitalCapabilities") }}
              </p>
              <n-divider />
              <h2 class="aira-type-card-title mb-0">
                {{ $t("page.research.resourceRequirements") }}
              </h2>
              <div v-if="task.resources.length" class="mt-3 space-y-2">
                <div v-for="resource in task.resources" :key="`${resource.source_id}:${resource.version}`" class="research-method">
                  <span class="aira-type-label">{{ resource.name }}</span>
                  <span class="aira-type-meta">r{{ resource.version }}</span>
                </div>
              </div>
              <p v-else class="aira-type-meta aira-text-muted mb-0 mt-3">
                {{ $t("page.research.noResourceRequirements") }}
              </p>
              <n-divider />
              <h2 class="aira-type-card-title mb-0">
                {{ $t("page.research.externalServices") }}
              </h2>
              <div v-if="task.services.length" class="mt-3 space-y-2">
                <div v-for="service in task.services" :key="service.source_revision_id" class="research-method">
                  <span class="aira-type-label">{{ service.metadata.provider.name }} · {{ service.name }}</span>
                  <span class="aira-type-meta">v{{ service.version }} · r{{ service.metadata.offering_revision }}</span>
                </div>
              </div>
              <p v-else class="aira-type-meta aira-text-muted mb-0 mt-3">
                {{ $t("page.research.noExternalServices") }}
              </p>
              <n-divider />
              <h2 class="aira-type-card-title mb-0">
                {{ $t("page.research.computeEnvironments") }}
              </h2>
              <div v-if="task.compute.length" class="mt-3 space-y-2">
                <div v-for="environment in task.compute" :key="environment.source_revision_id" class="research-method">
                  <span class="aira-type-label">{{ environment.name }}</span>
                  <span class="aira-type-meta">
                    r{{ environment.metadata.environment_revision }} · {{ environment.metadata.runtime_version }}
                  </span>
                </div>
              </div>
              <p v-else class="aira-type-meta aira-text-muted mb-0 mt-3">
                {{ $t("page.research.noComputeEnvironments") }}
              </p>
              <n-alert v-if="task.compute.length" type="info" class="mt-3">
                {{ $t("page.research.computePinnedOnlyHint") }}
              </n-alert>
              <n-divider />
              <h2 class="aira-type-card-title mb-0">
                {{ $t("page.research.resolvedExecutors") }}
              </h2>
              <div v-if="pinnedExecutorBindings.length" class="mt-3 space-y-2">
                <div v-for="binding in pinnedExecutorBindings" :key="binding.capability_key" class="research-method">
                  <span class="aira-type-label break-all">{{ binding.capability_key }}</span>
                  <span class="aira-type-meta">{{ binding.approval_policy.replaceAll("_", " ") }} · r{{ binding.revision }}</span>
                </div>
              </div>
              <div v-if="pinnedAutonomyPolicy" class="research-method mt-3">
                <span class="aira-type-label">{{ $t("page.research.researchPolicy") }}</span>
                <span class="aira-type-meta">
                  {{ pinnedAutonomyPolicy.source === "lab_policy" ? $t("page.research.labPolicy") : $t("page.research.platformDefaultPolicy") }}
                  · r{{ pinnedAutonomyPolicy.revision }}
                  · {{ pinnedAutonomyPolicy.policy_digest.slice(0, 12) }}
                </span>
              </div>
              <n-divider />
              <h2 class="aira-type-card-title mb-0">
                {{ $t("page.research.pinnedKnowledge") }}
              </h2>
              <n-collapse v-if="task.knowledge.length" class="mt-3">
                <n-collapse-item
                  v-for="item in task.knowledge"
                  :key="`${item.id}:${item.revision}`"
                  :title="item.title"
                  :name="item.id"
                >
                  <div class="flex flex-wrap gap-2">
                    <n-tag size="small" type="success">
                      {{ item.kind }}
                    </n-tag>
                    <n-tag size="small">
                      r{{ item.revision }}
                    </n-tag>
                  </div>
                  <p class="aira-type-body aira-text-secondary mb-0 mt-3 whitespace-pre-wrap">
                    {{ item.body }}
                  </p>
                </n-collapse-item>
              </n-collapse>
              <p v-else class="aira-type-meta aira-text-muted mb-0 mt-3">
                {{ $t("page.research.noKnowledge") }}
              </p>
              <div class="aira-type-meta mt-3">
                {{ $t("page.research.autonomy") }} · {{ autonomyLabel(task.autonomy_level) }}
              </div>
            </section>

            <section class="research-panel">
              <div class="aira-type-eyebrow">
                {{ $t("page.research.provenance") }}
              </div>
              <h2 class="aira-type-card-title mb-0 mt-1">
                {{ $t("page.research.timeline") }}
              </h2>
              <n-empty v-if="!task.events.length" class="py-5" :description="$t('page.research.noEvents')" />
              <div v-else class="mt-4 space-y-4">
                <div v-for="event in task.events.slice(0, 30)" :key="event.id" class="research-event">
                  <span class="research-event__dot" />
                  <div class="min-w-0">
                    <div class="aira-type-label">
                      {{ eventLabel(event.kind) }}
                    </div>
                    <div class="aira-type-meta mt-0.5">
                      <n-time :time="new Date(event.created_at)" type="relative" />
                    </div>
                  </div>
                </div>
              </div>
            </section>
          </aside>
        </div>
      </template>
    </n-spin>

    <n-modal
      v-model:show="actionModalVisible"
      preset="card"
      class="research-modal"
      :title="$t('page.research.addProtocolWork')"
      :mask-closable="false"
      @after-leave="resetActionDraft"
    >
      <template v-if="!actionPreview">
        <n-form label-placement="top">
          <n-form-item :label="$t('page.research.method')" required>
            <n-select v-model:value="actionDraft.protocol_id" :options="projectProtocolOptions" filterable />
          </n-form-item>
          <n-form-item :label="$t('page.research.workTitle')">
            <n-input v-model:value="actionDraft.title" />
          </n-form-item>
          <n-form-item :label="$t('page.research.instructions')">
            <n-input v-model:value="actionDraft.instructions" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" />
          </n-form-item>
          <n-form-item :label="$t('page.research.initialValues')">
            <n-input
              v-model:value="initialValuesText"
              type="textarea"
              :autosize="{ minRows: 3, maxRows: 10 }"
              placeholder="{}"
            />
            <template #feedback>
              {{ $t("page.research.initialValuesHint") }}
            </template>
          </n-form-item>
        </n-form>
      </template>
      <template v-else>
        <n-alert type="info">
          {{ $t("page.research.actionPreviewHint") }}
        </n-alert>
        <div class="research-preview mt-4">
          <div class="aira-type-eyebrow">
            {{ $t("page.research.saveDestination") }}
          </div>
          <h3 class="aira-type-card-title mb-0 mt-1">
            {{ actionPreview.destination.task.title }}
          </h3>
          <p class="aira-type-body aira-text-secondary mb-0 mt-2">
            {{ actionPreview.protocol.name }} · v{{ actionPreview.protocol.version }}
          </p>
          <div class="aira-type-meta mt-2">
            {{ $t("page.research.assignedTo") }} · {{ actionPreview.assignee.name || actionPreview.assignee.username }}
          </div>
        </div>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2">
          <n-button @click="actionPreview ? actionPreview = null : actionModalVisible = false">
            {{ actionPreview ? $t("page.research.backToEdit") : $t("common.cancel") }}
          </n-button>
          <n-button v-if="!actionPreview" type="primary" :disabled="!actionDraft.protocol_id" :loading="mutating" @click="previewAction">
            {{ $t("page.research.previewAction") }}
          </n-button>
          <n-button v-else type="primary" :loading="mutating" @click="createAction">
            {{ $t("page.research.confirmAction") }}
          </n-button>
        </div>
      </template>
    </n-modal>

    <n-modal v-model:show="reviewModalVisible" preset="card" class="research-modal" :title="$t('page.research.reviewResult')" :mask-closable="false">
      <n-alert type="warning" class="mb-4">
        {{ $t("page.research.reviewResponsibility") }}
      </n-alert>
      <section v-if="instanceStore.aiEnabled" class="reviewer-panel mb-4">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div>
            <div class="aira-type-label">
              {{ $t("page.research.independentReviewer") }}
            </div>
            <div class="aira-type-meta mt-1">
              {{ $t("page.research.independentReviewerHint") }}
            </div>
          </div>
          <n-button size="small" type="info" secondary :loading="reviewGenerating" @click="requestReviewRecommendation">
            {{ $t("page.research.runIndependentReview") }}
          </n-button>
        </div>
        <div v-if="reviewRecommendation" class="mt-3 border-t border-blue-100 pt-3">
          <div class="flex flex-wrap items-center gap-2">
            <n-tag size="small" type="info" round>
              {{ reviewerRecommendationLabel(reviewRecommendation.recommendation) }}
            </n-tag>
            <span class="aira-type-meta">{{ reviewRecommendation.model_name }}</span>
            <span class="aira-type-meta">
              {{ $t("page.research.reviewerEvidenceCounts", { supporting: reviewRecommendation.supporting_evidence_ids.length, contradicting: reviewRecommendation.contradicting_evidence_ids.length }) }}
            </span>
          </div>
          <p class="aira-type-body mb-0 mt-2 whitespace-pre-wrap">
            {{ reviewRecommendation.summary }}
          </p>
          <div v-if="reviewRecommendation.uncertainties.length || reviewRecommendation.missing_checks.length || reviewRecommendation.risk_flags.length" class="grid grid-cols-1 mt-3 gap-3 md:grid-cols-3">
            <div v-if="reviewRecommendation.uncertainties.length">
              <div class="aira-type-eyebrow">
                {{ $t("page.research.reviewerUncertainties") }}
              </div>
              <ul class="reviewer-list">
                <li v-for="item in reviewRecommendation.uncertainties" :key="item">
                  {{ item }}
                </li>
              </ul>
            </div>
            <div v-if="reviewRecommendation.missing_checks.length">
              <div class="aira-type-eyebrow">
                {{ $t("page.research.reviewerMissingChecks") }}
              </div>
              <ul class="reviewer-list">
                <li v-for="item in reviewRecommendation.missing_checks" :key="item">
                  {{ item }}
                </li>
              </ul>
            </div>
            <div v-if="reviewRecommendation.risk_flags.length">
              <div class="aira-type-eyebrow">
                {{ $t("page.research.reviewerRiskFlags") }}
              </div>
              <ul class="reviewer-list">
                <li v-for="item in reviewRecommendation.risk_flags" :key="item">
                  {{ item }}
                </li>
              </ul>
            </div>
          </div>
          <div class="mt-3 flex justify-end">
            <n-button size="small" type="primary" secondary @click="useReviewRecommendation">
              {{ $t("page.research.useReviewerDraft") }}
            </n-button>
          </div>
        </div>
      </section>
      <n-form label-placement="top">
        <n-form-item :label="$t('page.research.goalAssessment')" required>
          <n-select v-model:value="review.outcome" :options="outcomeOptions" />
        </n-form-item>
        <n-form-item :label="$t('page.research.scientificOutcome')" required>
          <n-select v-model:value="review.scientific_outcome" :options="scientificOutcomeOptions" />
        </n-form-item>
        <n-form-item :label="$t('page.research.reviewedConclusion')" required>
          <n-input v-model:value="review.conclusion" type="textarea" :autosize="{ minRows: 6, maxRows: 16 }" />
        </n-form-item>
      </n-form>
      <template #footer>
        <div class="flex justify-end gap-2">
          <n-button @click="reviewModalVisible = false">
            {{ $t("common.cancel") }}
          </n-button>
          <n-button type="primary" :disabled="!review.conclusion.trim() || reviewGenerating" :loading="mutating" @click="completeTask">
            {{ $t("page.research.confirmReview") }}
          </n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import type { ResearchToolDefinition } from "@/service/api/research-actions"
import type { ResearchAutonomyPolicySnapshot } from "@/service/api/research-autonomy-policies"
import type {
  HumanWorkItemStatus,
  ManualProtocolActionDraft,
  ManualProtocolActionPreview,
  ResearchAction,
  ResearchActionStatus,
  ResearchEnvironmentExecutorBinding,
  ResearchProtocolRef,
  ResearchResourceConsumption,
  ResearchReviewRecommendation,
  ResearchRun,
  ResearchRunOrigin,
  ResearchRunStatus,
  ResearchTaskDetail,
  ResearchTaskStatus,
} from "@/service/api/research-tasks"
import type { ProtocolModels } from "@airalogy/shared/types"
import type { TagProps } from "naive-ui"
import { fetchProtocols } from "@/service/api/project-protocols"
import {
  cancelResearchTask,
  completeResearchTask,
  createManualProtocolAction,
  fetchResearchTask,
  generateResearchReviewRecommendation,
  pauseResearchTask,
  previewManualProtocolAction,
  resumeResearchTask,
  startResearchTask,
  startResearchWorkItem,
} from "@/service/api/research-tasks"
import { useAuthStore } from "@/store/modules/auth"
import { useInstanceStore } from "@/store/modules/instance"
import { $t } from "@airalogy/shared/locales"
import { useDialog } from "naive-ui"
import { nanoid } from "nanoid"
import { useRoute, useRouter } from "vue-router"
import CreateResearchRunModal from "./components/create-research-run-modal.vue"
import ResearchActionImpact from "./components/research-action-impact.vue"
import ResearchApprovalActions from "./components/research-approval-actions.vue"
import ResearchAssetsPanel from "./components/research-assets-panel.vue"
import ResearchBudgetPanel from "./components/research-budget-panel.vue"
import ResearchComputeActionModal from "./components/research-compute-action-modal.vue"
import ResearchComputeJobActions from "./components/research-compute-job-actions.vue"
import ResearchDigitalActionModal from "./components/research-digital-action-modal.vue"
import ResearchHumanWorkActionModal from "./components/research-human-work-action-modal.vue"
import ResearchInstrumentStop from "./components/research-instrument-stop.vue"
import ResearchResourceActionModal from "./components/research-resource-action-modal.vue"
import ResearchResourceReservationActions from "./components/research-resource-reservation-actions.vue"
import ResearchResultPackagePanel from "./components/research-result-package-panel.vue"
import ResearchServiceActionModal from "./components/research-service-action-modal.vue"
import ResearchServiceJobActions from "./components/research-service-job-actions.vue"
import ResearchWaitEventSignal from "./components/research-wait-event-signal.vue"

const route = useRoute()
const router = useRouter()
const dialog = useDialog()
const authStore = useAuthStore()
const instanceStore = useInstanceStore()
const task = ref<ResearchTaskDetail | null>(null)
const loading = ref(false)
const loadError = ref(false)
const mutating = ref(false)
const startingWorkItemId = ref("")
const actionModalVisible = ref(false)
const actionPreview = ref<ManualProtocolActionPreview | null>(null)
const reviewModalVisible = ref(false)
const reviewGenerating = ref(false)
const reviewRecommendation = ref<ResearchReviewRecommendation | null>(null)
const selectedReviewRecommendationId = ref("")
const projectProtocols = ref<ProtocolModels.ProjectProtocolInfo[]>([])
const initialValuesText = ref("{}")
const actionDraft = reactive<ManualProtocolActionDraft>({
  protocol_id: "",
  title: "",
  instructions: "",
  initial_values: {},
  idempotency_key: "",
})
const review = reactive({
  outcome: "goal_met",
  scientific_outcome: "inconclusive",
  conclusion: "",
})
let pollTimer: ReturnType<typeof setInterval> | undefined

const latestRun = computed(() => task.value?.latest_run || task.value?.runs[0] || null)
const pinnedTools = computed<ResearchToolDefinition[]>(() => {
  const tools = latestRun.value?.environment_snapshot?.tools
  return Array.isArray(tools) ? tools as ResearchToolDefinition[] : []
})
const pinnedExecutorBindings = computed<ResearchEnvironmentExecutorBinding[]>(() => {
  const bindings = latestRun.value?.environment_snapshot?.executor_bindings
  return Array.isArray(bindings) ? bindings as ResearchEnvironmentExecutorBinding[] : []
})
const pinnedHumanWork = computed(() => {
  const capabilities = latestRun.value?.environment_snapshot?.human_work
  return Array.isArray(capabilities) ? capabilities : []
})
const pinnedAutonomyPolicy = computed<ResearchAutonomyPolicySnapshot | null>(() => {
  const policy = latestRun.value?.environment_snapshot?.autonomy_policy
  return policy && typeof policy === "object"
    ? policy as ResearchAutonomyPolicySnapshot
    : null
})
const hasAiraCapabilities = computed(() => Boolean(
  task.value?.protocols.length
  || pinnedHumanWork.value.some(item => item && typeof item === "object" && (item as { available?: boolean }).available !== false)
  || pinnedTools.value.some(item => item.available)
  || task.value?.resources.some(item => item.available)
  || task.value?.services.some(item => item.available),
))
const canAddAction = computed(() => ["active", "paused"].includes(task.value?.status || ""))
const canAddDigitalAction = computed(() => task.value?.status === "active")
const canAddServiceAction = computed(() => Boolean(
  task.value?.status === "active"
  && task.value.permissions.can_use_services
  && task.value.services.some(item => item.available),
))
const canAddComputeAction = computed(() => Boolean(
  task.value?.status === "active"
  && task.value.permissions.can_use_compute
  && task.value.compute.some(item => item.available),
))
const canCancel = computed(() => !["completed", "cancelled", "archived"].includes(task.value?.status || ""))
const canReview = computed(() => Boolean(
  task.value
  && task.value.status !== "completed"
  && task.value.status !== "cancelled"
  && task.value.open_work_items === 0
  && task.value.pending_approvals === 0
  && ["review_required", "active", "paused", "failed"].includes(task.value.status),
))
const canCreateRun = computed(() => Boolean(
  task.value?.permissions.can_run
  && latestRun.value
  && ["completed", "failed", "cancelled"].includes(task.value.status)
  && ["completed", "failed", "cancelled"].includes(latestRun.value.status),
))
const canManageBudget = computed(() => Boolean(
  task.value?.permissions.can_approve,
))
const canAmendLimits = computed(() => Boolean(
  canManageBudget.value
  && task.value
  && !["completed", "cancelled", "archived"].includes(task.value.status),
))
const openActions = computed(() => (task.value?.actions || []).filter(action =>
  action.work_item && ["open", "in_progress", "submitted", "changes_requested"].includes(action.work_item.status),
))
const pendingApprovalActions = computed(() => (task.value?.actions || []).filter(action =>
  action.approval?.status === "pending" && action.status === "proposed",
))
const resultConclusion = computed(() => task.value?.result_package.reviewed_conclusion
  || task.value?.conclusion
  || task.value?.result_package.narrative_conclusion
  || "")
const airaStage = computed(() => {
  const stage = String(latestRun.value?.aira_state?.path_status || "")
  return stage ? stage.replaceAll("_", " ") : $t("page.research.notStarted")
})
const taskStatusType = computed(() => statusType(task.value?.status || "draft"))
const projectProtocolOptions = computed(() => projectProtocols.value.map(protocol => ({
  label: `${protocol.name} · v${protocol.latest_version}`,
  value: String(protocol.id),
})))
const outcomeValues = [
  "goal_met",
  "goal_not_met_but_conclusive",
  "inconclusive",
  "blocked_missing_capability",
  "stopped_budget",
  "stopped_time",
  "stopped_safety",
  "cancelled",
  "execution_failed",
]
const scientificOutcomeValues = [
  "supports_hypothesis",
  "contradicts_hypothesis",
  "inconclusive",
  "unexpected",
  "not_applicable",
]
const outcomeOptions = computed(() => outcomeValues.map(value => ({ label: outcomeLabel(value), value })))
const scientificOutcomeOptions = computed(() => scientificOutcomeValues.map(value => ({ label: scientificOutcomeLabel(value), value })))

async function loadTask(silent = false) {
  if (!silent)
    loading.value = true
  loadError.value = false
  try {
    task.value = await fetchResearchTask(String(route.params.taskId))
  }
  catch {
    if (!silent)
      loadError.value = true
  }
  finally {
    loading.value = false
  }
}

async function mutate(operation: (current: ResearchTaskDetail) => Promise<ResearchTaskDetail>) {
  if (!task.value)
    return
  mutating.value = true
  try {
    task.value = await operation(task.value)
  }
  finally {
    mutating.value = false
  }
}

function startTask() {
  void mutate(current => startResearchTask(current.id, current.revision))
}

function resourceKindLabel(kind: "inventory" | "equipment") {
  return kind === "inventory"
    ? $t("page.research.inventoryReservation")
    : $t("page.research.equipmentBooking")
}

function formatDateTime(value?: string | null) {
  return value ? new Date(value).toLocaleString() : "—"
}

function pauseTask() {
  void mutate(current => pauseResearchTask(current.id, current.revision))
}

function resumeTask() {
  void mutate(current => resumeResearchTask(current.id, current.revision))
}

function cancelTask() {
  if (!task.value)
    return
  dialog.warning({
    title: $t("page.research.cancelTask"),
    content: $t("page.research.cancelConfirm"),
    positiveText: $t("page.research.cancelTask"),
    negativeText: $t("common.cancel"),
    onPositiveClick: () => mutate(current => cancelResearchTask(current.id, current.revision, "Cancelled by user")),
  })
}

async function loadProjectProtocols() {
  if (!task.value)
    return
  const result = await fetchProtocols({ page: 1, pageSize: 100, projectId: task.value.project_id })
  if (result.error)
    throw result.error
  projectProtocols.value = result.data?.protocols || []
}

async function openActionModal() {
  actionModalVisible.value = true
  if (!projectProtocols.value.length)
    await loadProjectProtocols()
  if (task.value?.protocols.length && !actionDraft.protocol_id)
    actionDraft.protocol_id = task.value.protocols[0].id
}

function resetActionDraft() {
  actionPreview.value = null
  actionDraft.protocol_id = ""
  actionDraft.title = ""
  actionDraft.instructions = ""
  actionDraft.initial_values = {}
  actionDraft.idempotency_key = ""
  initialValuesText.value = "{}"
}

function parsedInitialValues() {
  try {
    const value = JSON.parse(initialValuesText.value || "{}")
    if (!value || typeof value !== "object" || Array.isArray(value))
      throw new Error("Initial values must be a JSON object")
    return value as Record<string, unknown>
  }
  catch {
    window.$message?.error($t("page.research.invalidInitialValues"))
    return null
  }
}

async function previewAction() {
  if (!task.value || !actionDraft.protocol_id)
    return
  const initialValues = parsedInitialValues()
  if (!initialValues)
    return
  mutating.value = true
  try {
    actionDraft.initial_values = initialValues
    actionDraft.idempotency_key ||= `manual-${nanoid(16)}`
    actionPreview.value = await previewManualProtocolAction(task.value.id, { ...actionDraft })
  }
  finally {
    mutating.value = false
  }
}

async function createAction() {
  if (!task.value || !actionPreview.value)
    return
  mutating.value = true
  try {
    await createManualProtocolAction(task.value.id, {
      ...actionDraft,
      preview_digest: actionPreview.value.preview_digest,
    })
    actionModalVisible.value = false
    window.$message?.success($t("page.research.actionCreated"))
    await loadTask(true)
  }
  finally {
    mutating.value = false
  }
}

async function executeWorkItem(action: ResearchAction) {
  if (!action.work_item || !task.value)
    return
  if (action.kind === "human_work_item") {
    await router.push({
      name: "research-work-item-detail",
      params: { workItemId: action.work_item.id },
    })
    return
  }
  if (!action.protocol)
    return
  startingWorkItemId.value = action.work_item.id
  try {
    if (["open", "changes_requested"].includes(action.work_item.status))
      await startResearchWorkItem(action.work_item.id, action.work_item.revision)
    await router.push({
      name: "add-protocol-record",
      params: {
        labUid: action.protocol.lab_uid || task.value.lab.uid,
        projectUid: action.protocol.project_uid || task.value.project.uid,
        protocolUid: action.protocol.uid,
      },
      query: { researchWorkItem: action.work_item.id },
    })
  }
  finally {
    startingWorkItemId.value = ""
  }
}

function canExecuteAction(action: ResearchAction) {
  if (action.kind === "human_work_item") {
    return Boolean(
      action.work_item
      && (
        (
          String(action.work_item.assignee_user_id) === String(authStore.userInfo.id)
          && ["open", "in_progress", "changes_requested"].includes(action.work_item.status)
        )
        || (
          action.work_item.status === "submitted"
          && (
            String(task.value?.owner_user_id) === String(authStore.userInfo.id)
            || task.value?.permissions.can_approve
          )
        )
      ),
    )
  }
  return Boolean(
    action.work_item
    && action.protocol
    && String(action.work_item.assignee_user_id) === String(authStore.userInfo.id)
    && ["open", "in_progress", "changes_requested"].includes(action.work_item.status),
  )
}

function actionWorkLabel(action: ResearchAction) {
  if (action.kind !== "human_work_item")
    return $t("page.research.executeProtocol")
  return action.work_item?.status === "submitted"
    ? $t("page.research.reviewSubmission")
    : $t("page.research.completeHumanWork")
}

function instrumentRiskType(risk: "read_only" | "low" | "medium" | "high") {
  if (risk === "high")
    return "error"
  if (risk === "medium")
    return "warning"
  return "info"
}

function instrumentJobStatusLabel(status: string) {
  return $t(`page.research.instrumentJobStatus.${status}` as I18n.I18nKey)
}

function computeJobStatusLabel(status: string) {
  return $t(`page.research.computeJobStatus.${status}` as I18n.I18nKey)
}

function computeOutputStatusLabel(status: string) {
  return $t(`page.research.computeOutputStatus.${status}` as I18n.I18nKey)
}

function formatFileSize(bytes: number) {
  if (bytes < 1024)
    return `${bytes} B`
  const units = ["KB", "MB", "GB"]
  let value = bytes / 1024
  let index = 0
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024
    index += 1
  }
  return `${value >= 10 ? value.toFixed(0) : value.toFixed(1)} ${units[index]}`
}

function openReviewModal() {
  if (!task.value)
    return
  review.outcome = task.value.outcome || "goal_met"
  review.scientific_outcome = task.value.scientific_outcome || "inconclusive"
  review.conclusion = resultConclusion.value
  reviewRecommendation.value = (task.value.review_recommendations || [])[0] || null
  selectedReviewRecommendationId.value = ""
  reviewModalVisible.value = true
}

async function requestReviewRecommendation() {
  if (!task.value)
    return
  reviewGenerating.value = true
  try {
    const recommendation = await generateResearchReviewRecommendation(task.value.id, task.value.revision)
    reviewRecommendation.value = recommendation
    task.value.review_recommendations ||= []
    if (!task.value.review_recommendations.some(item => item.id === recommendation.id))
      task.value.review_recommendations.unshift(recommendation)
    window.$message?.success($t("page.research.independentReviewReady"))
  }
  finally {
    reviewGenerating.value = false
  }
}

function useReviewRecommendation() {
  if (!reviewRecommendation.value)
    return
  review.outcome = reviewRecommendation.value.recommended_task_outcome
  review.scientific_outcome = reviewRecommendation.value.recommended_scientific_outcome
  review.conclusion = reviewRecommendation.value.summary
  selectedReviewRecommendationId.value = reviewRecommendation.value.id
}

async function completeTask() {
  if (!task.value || !review.conclusion.trim())
    return
  mutating.value = true
  try {
    task.value = await completeResearchTask(task.value.id, {
      expected_revision: task.value.revision,
      outcome: review.outcome,
      scientific_outcome: review.scientific_outcome,
      conclusion: review.conclusion.trim(),
      review_recommendation_id: selectedReviewRecommendationId.value || undefined,
    })
    reviewModalVisible.value = false
    window.$message?.success($t("page.research.reviewCompleted"))
  }
  finally {
    mutating.value = false
  }
}

function reviewerRecommendationLabel(value: ResearchReviewRecommendation["recommendation"]) {
  return $t(`page.research.reviewerRecommendation.${value}` as I18n.I18nKey)
}

function goBack() {
  void router.push({ name: "research-tasks" })
}

function openProtocol(protocol: ResearchProtocolRef) {
  if (!task.value)
    return
  void router.push({
    name: "protocol-detail",
    params: {
      labUid: task.value.lab.uid,
      projectUid: task.value.project.uid,
      protocolUid: protocol.uid,
    },
  })
}

function openRecord(action: ResearchAction) {
  if (!task.value || !action.protocol_run?.record_id || !action.protocol_run.record_version || !action.protocol)
    return
  void router.push({
    name: "protocol-record-report",
    params: {
      labUid: task.value.lab.uid,
      projectUid: task.value.project.uid,
      protocolUid: action.protocol.uid,
      protocolVersion: action.protocol_run.protocol_version,
      recordId: action.protocol_run.record_id,
      recordVersion: String(action.protocol_run.record_version),
    },
  })
}

function openResourceConsumptionRecord(consumption: ResearchResourceConsumption) {
  if (!task.value)
    return
  void router.push({
    name: "protocol-record-report",
    params: {
      labUid: task.value.lab.uid,
      projectUid: task.value.project.uid,
      protocolUid: consumption.protocol_uid,
      protocolVersion: consumption.protocol_version,
      recordId: consumption.record_id,
      recordVersion: String(consumption.record_version),
    },
  })
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

function runStatusType(status: ResearchRunStatus): TagProps["type"] {
  if (status === "completed")
    return "success"
  if (status === "failed" || status === "cancelled")
    return "error"
  if (status.startsWith("waiting"))
    return "warning"
  return "info"
}

function actionStatusType(status: ResearchActionStatus): TagProps["type"] {
  if (status === "completed")
    return "success"
  if (status === "failed" || status === "cancelled")
    return "error"
  if (status === "waiting" || status === "blocked")
    return "warning"
  return "info"
}

function actionDependencyLabel(action: ResearchAction) {
  return action.dependencies
    .map((dependency) => {
      const parent = task.value?.actions.find(item => item.id === dependency.action_id)
      return parent ? `#${parent.sequence} ${parent.title}` : dependency.action_id
    })
    .join(", ")
}

function taskStatusLabel(status: ResearchTaskStatus) {
  return $t(`page.research.taskStatus.${status}` as I18n.I18nKey)
}

function runStatusLabel(status: ResearchRunStatus) {
  return $t(`page.research.runStatus.${status}` as I18n.I18nKey)
}

function runOrigin(run: ResearchRun): ResearchRunOrigin | null {
  const origin = run.environment_snapshot?.run_origin
  if (!origin || typeof origin !== "object" || Array.isArray(origin))
    return null
  return origin as unknown as ResearchRunOrigin
}

function runKindLabel(run: ResearchRun) {
  const kind = runOrigin(run)?.kind || "initial"
  return $t(`page.research.runKinds.${kind}` as I18n.I18nKey)
}

function runConclusion(run: ResearchRun) {
  return run.result_package.reviewed_conclusion
    || run.result_package.narrative_conclusion
    || ""
}

function actionStatusLabel(status: ResearchActionStatus) {
  return $t(`page.research.actionStatus.${status}` as I18n.I18nKey)
}

function toolResultItems(action: ResearchAction): Array<Record<string, any>> {
  const items = action.tool_job?.output?.items
  return Array.isArray(items) ? items : []
}

function formatPayload(payload: Record<string, any>) {
  return JSON.stringify(payload || {}, null, 2)
}

function autonomyLabel(level: ResearchTaskDetail["autonomy_level"]) {
  const key = level === "assisted" ? "autonomyAssisted" : level === "bounded_autopilot" ? "autonomyBounded" : "autonomyPolicy"
  return $t(`page.research.${key}` as I18n.I18nKey)
}

function outcomeLabel(value: string) {
  return $t(`page.research.outcome.${value}` as I18n.I18nKey)
}

function scientificOutcomeLabel(value: string) {
  return $t(`page.research.scientificOutcomeValue.${value}` as I18n.I18nKey)
}

function eventLabel(kind: string) {
  const known = [
    "task.created",
    "run.created",
    "run.started",
    "run.paused",
    "run.resumed",
    "run.completed",
    "run.failed",
    "task.cancelled",
    "task.completed",
    "task.review_requested",
    "plan.version_created",
    "aira.step_completed",
    "aira.action_proposed",
    "work_item.assigned",
    "work_item.started",
    "work_item.submitted",
    "work_item.changes_requested",
    "work_item.completed",
    "approval.requested",
    "approval.approved",
    "approval.rejected",
    "run.manual_control_required",
    "data_asset.created",
    "data_asset.version_created",
    "data_asset.status_changed",
    "evidence.registered",
    "evidence.reviewed",
    "claim.created",
    "claim.revised",
    "claim.reviewed",
    "protocol_improvement.suggested",
    "protocol_improvement.reviewed",
    "protocol_improvement.applied",
    "tool_job.queued",
    "tool_job.started",
    "tool_job.completed",
    "tool_job.failed",
    "instrument_job.queued",
    "instrument_job.leased",
    "instrument_job.started",
    "instrument_job.stop_requested",
    "instrument_job.completed",
    "instrument_job.failed",
    "instrument_job.stopped",
    "compute_job.requested",
    "compute_job.queued",
    "compute_job.leased",
    "compute_job.input_downloaded",
    "compute_job.started",
    "compute_output.uploaded",
    "compute_job.cancel_requested",
    "compute_job.completed",
    "compute_job.failed",
    "compute_job.cancelled",
    "wait_event.created",
    "wait_event.received",
    "external_service.quote_requested",
    "external_service.catalog_quote_created",
    "external_service.quote_recorded",
    "external_service.order_approved",
    "external_service.in_fulfillment",
    "external_service.custody_recorded",
    "external_service.failed",
    "external_service.completed",
  ]
  return known.includes(kind)
    ? $t(`page.research.event.${kind.replaceAll(".", "_")}` as I18n.I18nKey)
    : kind.replaceAll(".", " · ").replaceAll("_", " ")
}

function startPolling() {
  pollTimer = setInterval(() => {
    if (task.value && ["active", "review_required"].includes(task.value.status))
      void loadTask(true)
  }, 5000)
}

onMounted(async () => {
  await loadTask()
  startPolling()
})
onUnmounted(() => {
  if (pollTimer)
    clearInterval(pollTimer)
})
</script>

<style scoped>
.research-detail {
  width: 100%;
}

.research-detail__hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1.5rem;
  border: 1px solid rgb(219 234 254);
  border-radius: 1rem;
  background: linear-gradient(135deg, rgb(var(--primary-color) / 9%), white 70%);
  padding: clamp(1.25rem, 3vw, 2rem);
}

.research-panel {
  border: 1px solid rgb(229 231 235);
  border-radius: 0.875rem;
  background: white;
  padding: 1.25rem;
}

.research-panel--attention {
  border-color: rgb(251 191 36 / 55%);
  background: rgb(255 251 235 / 72%);
}

.research-metric {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 0.25rem;
  border-radius: 0.75rem;
  background: rgb(249 250 251);
  padding: 0.875rem;
}

.research-action-card,
.research-run-card,
.research-preview {
  border: 1px solid rgb(219 234 254);
  border-radius: 0.75rem;
  background: rgb(var(--primary-color) / 4%);
  padding: 1rem;
}

.research-digital-result {
  border: 1px solid rgb(226 232 240);
  border-radius: 0.75rem;
  background: rgb(248 250 252);
  padding: 0.75rem;
}

.research-tool-result {
  border-radius: 0.625rem;
  background: white;
  padding: 0.625rem 0.75rem;
}

.research-consumption {
  display: flex;
  width: 100%;
  flex-direction: column;
  gap: 0.2rem;
  border: 1px solid rgb(226 232 240);
  border-radius: 0.625rem;
  background: white;
  padding: 0.625rem 0.75rem;
  text-align: left;
}

.research-consumption:hover,
.research-consumption:focus-visible {
  border-color: rgb(var(--primary-color) / 45%);
  outline: none;
}

.research-digital-result pre {
  margin: 0.625rem 0 0;
  overflow: auto;
  border-radius: 0.625rem;
  background: rgb(15 23 42);
  color: rgb(226 232 240);
  font-size: 0.75rem;
  line-height: 1.55;
  padding: 0.75rem;
}

.research-sequence {
  display: flex;
  width: 1.75rem;
  height: 1.75rem;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  border-radius: 9999px;
  background: rgb(var(--primary-color) / 10%);
  color: rgb(var(--primary-color));
  font-weight: 600;
}

.research-method {
  display: flex;
  width: 100%;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  border: 1px solid rgb(229 231 235);
  border-radius: 0.625rem;
  padding: 0.75rem;
  text-align: left;
}

.research-method:hover,
.research-method:focus-visible {
  border-color: rgb(var(--primary-color) / 45%);
  outline: none;
}

.research-event {
  position: relative;
  display: flex;
  gap: 0.75rem;
}

.research-event__dot {
  width: 0.625rem;
  height: 0.625rem;
  flex: 0 0 auto;
  border: 2px solid white;
  border-radius: 9999px;
  background: rgb(var(--primary-color));
  box-shadow: 0 0 0 2px rgb(var(--primary-color) / 18%);
  margin-top: 0.3rem;
}

.research-modal {
  width: min(44rem, calc(100vw - 2rem));
}

.reviewer-panel {
  border: 1px solid rgb(191 219 254);
  border-radius: 0.75rem;
  background: rgb(239 246 255 / 65%);
  padding: 1rem;
}

.reviewer-list {
  margin: 0.5rem 0 0;
  padding-left: 1.1rem;
  color: rgb(75 85 99);
  font-size: 0.8125rem;
  line-height: 1.5;
}

@media (max-width: 48rem) {
  .research-detail__hero {
    flex-direction: column;
  }
}
</style>

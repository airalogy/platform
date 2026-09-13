<template>
  <div class="workflow-page py-8" data-testid="workflow-workbench">
    <header class="mb-5 flex flex-wrap items-start justify-between gap-3">
      <div class="min-w-0">
        <h1 class="aira-type-page-title m-0">
          {{ $t("page.workflowDefinitions.title") }}
        </h1>
        <p class="aira-type-body aira-text-secondary mt-2 max-w-3xl">
          {{ $t("page.workflowDefinitions.description") }}
        </p>
      </div>
      <n-button :loading="loading" :disabled="busy" @click="refresh">
        {{ $t("common.refresh") }}
      </n-button>
    </header>
    <n-alert type="info" class="mb-4">
      {{ $t("page.workflowDefinitions.scopeHint") }}
    </n-alert>
    <n-alert v-if="error" type="error" class="mb-4" data-testid="workflow-error">
      {{ error }}
    </n-alert>
    <n-alert v-if="context?.analysis_method_warnings?.length" type="warning" class="mb-4">
      {{ $t('page.workflowAnalysis.unavailableMethods') }}
    </n-alert>
    <n-alert v-if="notice" type="success" class="mb-4" data-testid="workflow-result">
      {{ notice }}
    </n-alert>
    <n-spin :show="loading">
      <div v-if="context" class="workflow-workspace">
        <aside class="workflow-panel workflow-library">
          <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h2 class="aira-type-section-title m-0">
              {{ $t("page.workflowDefinitions.savedWorkflows") }}
            </h2>
            <n-button v-if="context.capabilities.write" size="small" :disabled="busy" data-testid="workflow-new" @click="startNew">
              {{ $t("page.workflowDefinitions.newWorkflow") }}
            </n-button>
          </div>
          <n-empty v-if="!definitions.length" :description="$t('page.workflowDefinitions.noWorkflows')" />
          <div v-else class="workflow-definition-list">
            <button
              v-for="item in definitions" :key="item.id" type="button" class="workflow-library-item"
              :class="{ 'workflow-library-item--selected': detail?.id === item.id }"
              :aria-current="detail?.id === item.id ? 'true' : undefined" :disabled="busy"
              data-testid="workflow-saved-item" @click="openDefinition(item.id)"
            >
              <strong>{{ item.title }}</strong>
              <span class="aira-type-meta aira-text-secondary">{{ $t("page.workflowDefinitions.revision", { number: item.revision }) }}</span>
            </button>
          </div>
          <p class="aira-type-meta aira-text-secondary mt-4">
            {{ $t("page.workflowDefinitions.legacyHint") }}
          </p>
          <n-button v-if="context.capabilities.write" :disabled="busy" size="small" data-testid="workflow-convert-legacy" @click="openConversion">
            {{ $t('page.workflowLegacy.entry') }}
          </n-button>
        </aside>

        <main class="min-w-0">
          <section class="workflow-panel">
            <n-alert v-if="!context.capabilities.write" type="info" class="mb-4">
              {{ $t("page.workflowDefinitions.readOnly") }}
            </n-alert>
            <div v-if="detail" class="mb-4 flex flex-wrap items-center gap-3">
              <n-select
                :value="revisionId" :options="revisionOptions" :disabled="busy" class="workflow-revision-select"
                :aria-label="$t('page.workflowDefinitions.savedRevision')" data-testid="workflow-revision"
                @update:value="selectRevision"
              />
              <n-tag v-if="dirty" type="warning">
                {{ $t("page.workflowDefinitions.unsaved") }}
              </n-tag>
              <span v-else class="aira-type-meta aira-text-secondary">{{ $t("page.workflowDefinitions.immutableHint") }}</span>
            </div>
            <n-form label-placement="top" :disabled="!editable">
              <n-form-item :label="$t('page.workflowDefinitions.workflowTitle')" required>
                <n-input v-model:value="title" :maxlength="255" data-testid="workflow-title" />
              </n-form-item>
              <n-form-item :label="$t('page.workflowDefinitions.workflowDescription')">
                <n-input v-model:value="description" type="textarea" :maxlength="4000" :autosize="{ minRows: 2, maxRows: 4 }" data-testid="workflow-description" />
              </n-form-item>
            </n-form>
            <n-radio-group v-model:value="addKind" :disabled="!editable" class="mb-3" data-testid="workflow-card-kind">
              <n-radio value="protocol">
                {{ $t('page.workflowAnalysis.protocolCard') }}
              </n-radio>
              <n-radio value="analysis">
                {{ $t('page.workflowAnalysis.analysisCard') }}
              </n-radio>
            </n-radio-group>
            <div v-if="addKind === 'protocol'" class="workflow-add-row mb-4">
              <n-select
                v-model:value="addProtocolId" :options="protocolOptions" filterable :disabled="!editable"
                :placeholder="$t('page.workflowDefinitions.selectProtocol')" :aria-label="$t('page.workflowDefinitions.selectProtocol')"
                data-testid="workflow-add-protocol"
              />
              <n-button :disabled="!editable || !addProtocolId || graph.nodes.length >= 40" data-testid="workflow-add-card" @click="addCard">
                {{ $t("page.workflowDefinitions.addCard") }}
              </n-button>
            </div>
            <div v-else class="mb-4">
              <div class="workflow-add-row mb-3">
                <n-select v-model:value="addMethodId" :options="methodOptions" :disabled="!editable" filterable :placeholder="$t('page.workflowAnalysis.selectMethod')" data-testid="workflow-add-analysis-method" />
                <n-button :disabled="!editable || !addMethodId || graph.nodes.length >= 40" data-testid="workflow-add-analysis-card" @click="addAnalysisCard">
                  {{ $t('page.workflowAnalysis.addCard') }}
                </n-button>
              </div>
              <n-button :disabled="!editable" data-testid="workflow-publish-method" @click="publishMethodVisible = true">
                {{ $t('page.workflowAnalysis.publishAction') }}
              </n-button>
              <p class="aira-type-meta">
                {{ $t('page.workflowAnalysis.computeSupported') }}
              </p>
            </div>
            <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h2 class="aira-type-section-title m-0">
                {{ $t("page.workflowDefinitions.cards", { count: graph.nodes.length }) }}
              </h2>
              <div class="flex flex-wrap gap-2">
                <n-button v-if="!narrow" :type="viewMode === 'canvas' ? 'primary' : 'default'" size="small" data-testid="workflow-view-canvas" @click="viewMode = 'canvas'">
                  {{ $t("page.workflowDefinitions.canvas") }}
                </n-button>
                <n-button :type="effectiveView === 'list' ? 'primary' : 'default'" size="small" data-testid="workflow-view-list" @click="viewMode = 'list'">
                  {{ $t("page.workflowDefinitions.list") }}
                </n-button>
                <n-button v-if="effectiveView === 'canvas'" :disabled="!editable || !graph.nodes.length" size="small" @click="arrange">
                  {{ $t("page.workflowDefinitions.arrange") }}
                </n-button>
              </div>
            </div>
            <p class="aira-type-meta aira-text-secondary mt-0">
              {{ $t("page.workflowDefinitions.dependencyHint") }}
            </p>
            <n-empty v-if="!graph.nodes.length" :description="$t('page.workflowDefinitions.noCards')" class="py-8" />
            <workflow-canvas
              v-else-if="effectiveView === 'canvas'" :graph="graph" :protocols="context.protocols" :methods="context.analysis_methods" :disabled="!editable" :selected-id="selectedNodeId"
              @select="selectedNodeId = $event" @connect="connectCards" @positions="updatePositions"
            />
            <div v-else class="workflow-cards" data-testid="workflow-card-list">
              <article v-for="(node, index) in graph.nodes" :key="node.node_id" class="workflow-card" :data-node-id="node.node_id">
                <div class="flex flex-wrap items-center justify-between gap-2">
                  <div class="min-w-0">
                    <div class="aira-type-meta aira-text-secondary">
                      {{ $t("page.workflowDefinitions.cardNumber", { number: index + 1 }) }}
                    </div>
                    <h3 class="aira-type-card-title mb-1 mt-0">
                      {{ node.title }}
                    </h3>
                    <p class="aira-type-meta m-0">
                      {{ cardResourceLabel(node) }}
                    </p>
                  </div>
                  <n-button size="small" :type="selectedNodeId === node.node_id ? 'primary' : 'default'" :disabled="busy" @click="selectedNodeId = selectedNodeId === node.node_id ? null : node.node_id">
                    {{ $t("page.workflowDefinitions.configureCard") }}
                  </n-button>
                </div>
                <div class="aira-type-meta aira-text-secondary mt-3">
                  {{ $t("page.workflowDefinitions.dependsOn") }}: {{ incomingTitles(node.node_id) }}
                </div>
                <div v-if="editable" class="mt-3 flex flex-wrap gap-2">
                  <n-button size="tiny" :disabled="index === 0" @click="moveCard(node.node_id, -1)">
                    {{ $t("page.workflowDefinitions.moveUp") }}
                  </n-button>
                  <n-button size="tiny" :disabled="index === graph.nodes.length - 1" @click="moveCard(node.node_id, 1)">
                    {{ $t("page.workflowDefinitions.moveDown") }}
                  </n-button>
                  <n-button size="tiny" :disabled="graph.nodes.length >= 40" data-testid="workflow-duplicate-card" @click="duplicateCard(node)">
                    {{ $t("page.workflowDefinitions.duplicateCard") }}
                  </n-button>
                  <n-button size="tiny" @click="removeCard(node.node_id)">
                    {{ $t("common.delete") }}
                  </n-button>
                </div>
              </article>
            </div>

            <section v-if="selectedNode" class="workflow-node-settings mt-4" data-testid="workflow-card-settings">
              <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
                <h3 class="aira-type-card-title m-0">
                  {{ $t("page.workflowDefinitions.configureCard") }}
                </h3>
                <n-button size="small" @click="selectedNodeId = null">
                  {{ $t("common.close") }}
                </n-button>
              </div>
              <n-form label-placement="top" :disabled="!editable">
                <n-form-item :label="$t('page.workflowDefinitions.cardTitle')" required>
                  <n-input v-model:value="selectedNode.title" :maxlength="255" data-testid="workflow-card-title" />
                </n-form-item>
                <n-form-item v-if="selectedNode.kind === 'protocol'" :label="$t('page.workflowDefinitions.protocolVersion')" required>
                  <n-select v-model:value="selectedNode.protocol_version_id" :options="versionOptions(selectedNode)" data-testid="workflow-card-version" />
                </n-form-item>
                <n-form-item v-else :label="$t('page.workflowAnalysis.methodSnapshot')" required>
                  <n-select :value="selectedNode.method_publication_id" :options="methodOptions" data-testid="workflow-card-method" @update:value="selectAnalysisMethod" />
                  <template #feedback>
                    {{ $t('page.workflowAnalysis.changeMethodHint') }}
                  </template>
                </n-form-item>
                <n-form-item :label="$t('page.workflowDefinitions.dependsOn')">
                  <n-select
                    :value="incomingIds(selectedNode.node_id)" :options="dependencyOptions" multiple clearable
                    :placeholder="$t('page.workflowDefinitions.startIndependently')" data-testid="workflow-card-dependencies"
                    @update:value="setDependencies"
                  />
                  <template #feedback>
                    {{ $t("page.workflowDefinitions.joinHint") }}
                  </template>
                </n-form-item>
              </n-form>
              <section v-if="incomingEdges(selectedNode.node_id).length" class="mb-4">
                <h4 class="aira-type-label mb-2 mt-0">
                  {{ $t("page.workflowDefinitions.conditions.title") }}
                </h4>
                <p class="aira-type-meta aira-text-secondary mt-0">
                  {{ $t("page.workflowDefinitions.conditions.hint") }}
                </p>
                <div class="grid gap-3">
                  <workflow-edge-condition
                    v-for="edge in incomingEdges(selectedNode.node_id)" :key="edge.edge_id" :edge="edge"
                    :fields="workflowScalarFields(fieldsForNode(edge.source_node_id))" :source-title="nodeTitle(edge.source_node_id)" :target-title="selectedNode.title"
                    :disabled="!editable" @change="condition => updateCondition(edge.edge_id, condition)"
                  />
                </div>
              </section>
              <workflow-analysis-inputs v-if="selectedNode.kind === 'analysis'" :graph="graph" :node="selectedNode" :method="analysisMethod(selectedNode.method_publication_id)" :disabled="!editable" @sources="selectedNode.record_sources = $event" @outputs="updateBuiltinOutputs" @compute-outputs="updateComputeOutputs" @compute-files="updateComputeFiles" />
              <n-alert v-if="selectedNode.kind === 'analysis' && outputCatalogs[selectedNode.node_id]?.pending" type="info" class="mt-3">
                {{ $t('page.workflowAnalysis.previewOutputs') }}
              </n-alert>
              <n-alert v-if="selectedNode.kind === 'analysis' && outputCatalogs[selectedNode.node_id]?.error" type="error" class="mt-3">
                {{ outputCatalogs[selectedNode.node_id].error }}
                <n-button class="mt-2" size="small" :disabled="!editable" @click="loadOutputCatalog(selectedNode)">
                  {{ $t('common.retry') }}
                </n-button>
              </n-alert>
              <workflow-node-bindings
                v-if="selectedNode.kind === 'protocol'" :graph="graph" :node="selectedNode" :protocols="context.protocols" :analysis-fields="analysisFields" :disabled="!editable"
                class="mb-4" @change="updateBindings"
              />
              <div v-if="selectedNode.kind === 'protocol' && Object.keys(selectedNode.initial_values).length" class="mb-4">
                <h4 class="aira-type-label mb-2">
                  {{ $t("page.workflowDefinitions.initialValues") }}
                </h4>
                <pre class="workflow-initial-values" tabindex="0">{{ JSON.stringify(selectedNode.initial_values, null, 2) }}</pre>
              </div>
              <div v-if="effectiveView === 'canvas' && editable" class="flex flex-wrap gap-2">
                <n-button :disabled="graph.nodes.length >= 40" size="small" @click="duplicateCard(selectedNode)">
                  {{ $t("page.workflowDefinitions.duplicateCard") }}
                </n-button>
                <n-button size="small" @click="removeCard(selectedNode.node_id)">
                  {{ $t("common.delete") }}
                </n-button>
              </div>
              <p class="aira-type-meta aira-text-secondary mb-0 break-all">
                {{ $t("page.workflowDefinitions.stableId") }}: {{ selectedNode.node_id }}
              </p>
            </section>

            <n-alert v-if="graphProblem && graph.nodes.length" type="warning" class="mt-4" data-testid="workflow-graph-warning">
              {{ $t(`page.workflowDefinitions.validation.${graphProblem}`) }}
            </n-alert>
            <div class="mt-5 flex flex-wrap gap-2">
              <n-button v-if="context.capabilities.write" type="primary" :disabled="!editable || !title.trim() || !!graphProblem || !dirty" :loading="busy" data-testid="workflow-preview-save" @click="previewSave">
                {{ $t("page.workflowDefinitions.previewSave") }}
              </n-button>
              <n-button v-if="detail && context.capabilities.run" :disabled="busy || dirty || !revisionId" data-testid="workflow-open-run" @click="openRunDialog">
                {{ $t("page.workflowDefinitions.prepareRun") }}
              </n-button>
            </div>
            <p v-if="dirty && detail" class="aira-type-meta aira-text-secondary mb-0">
              {{ $t("page.workflowDefinitions.saveBeforeRun") }}
            </p>
          </section>
          <section v-if="detail" class="workflow-panel mt-5">
            <h2 class="aira-type-section-title mt-0">
              {{ $t("page.workflowDefinitions.runs") }}
            </h2>
            <n-empty v-if="!detail.runs.length" :description="$t('page.workflowDefinitions.noRuns')" />
            <div v-for="run in detail.runs" :key="run.run_id" class="workflow-run-row">
              <div class="min-w-0">
                <strong>{{ taskTitle(run.task_id) }}</strong>
                <div class="aira-type-meta aira-text-secondary break-all">
                  {{ $t("page.workflowDefinitions.revision", { number: detail.revisions.find(revision => revision.id === run.workflow_revision_id)?.revision ?? "—" }) }} · {{ runStatus(run.status) }}
                </div>
              </div>
              <n-button size="small" @click="router.push({ name: 'research-task-detail', params: { taskId: run.task_id } })">
                {{ $t("page.workflowDefinitions.openRun") }}
              </n-button>
              <ul v-if="run.actions?.length" class="workflow-run-actions">
                <li v-for="action in run.actions" :key="action.id" :data-skip-reason="action.skip_reason ?? undefined">
                  <strong>{{ action.title }}</strong> · {{ actionStatus(action.status, action.skip_reason) }}
                </li>
              </ul>
            </div>
          </section>
        </main>
      </div>
    </n-spin>
    <analysis-method-publish-modal v-if="projectInfo" v-model:show="publishMethodVisible" :project-id="projectInfo.id" :project-name="projectInfo.name" @published="methodPublished" />

    <n-modal v-model:show="saveVisible" preset="card" class="aira-dialog" style="--aira-dialog-width: 44rem" :title="$t('page.workflowDefinitions.savePreview')" :mask-closable="false" :closable="!busy && !confirmationUncertain" :close-on-esc="!busy && !confirmationUncertain">
      <template v-if="savePreview">
        <n-alert type="info" class="mb-4">
          {{ $t("page.workflowDefinitions.saveImpact", { project: projectInfo?.name, revision: (savePreview.expected_revision ?? 0) + 1 }) }}
        </n-alert>
        <n-alert v-if="error" type="error" class="mb-4">
          {{ error }}
        </n-alert>
        <n-alert v-if="confirmationUncertain" type="warning" class="mb-4">
          {{ $t("page.workflowDefinitions.confirmationUncertain") }}
        </n-alert>
        <h3 class="aira-type-card-title break-words">
          {{ savePreview.title }}
        </h3>
        <p>{{ $t("page.workflowDefinitions.graphSummary", { nodes: savePreview.graph.nodes.length, edges: savePreview.graph.edges.length }) }}</p>
        <ol class="workflow-preview-pins">
          <li v-for="pin in savePreview.pins" :key="pin.node_id">
            <strong>{{ savePreview.graph.nodes.find(node => node.node_id === pin.node_id)?.title }}</strong>
            <span>{{ pin.name }} · {{ pin.kind === 'analysis' ? `${pin.engine_version} · ${pin.content_digest}` : pin.version }}</span>
          </li>
        </ol>
        <workflow-data-summary :graph="savePreview.graph" :methods="context?.analysis_methods" :field-catalog="fieldCatalog" />
        <template v-for="node in savePreview.graph.nodes" :key="node.node_id">
          <div v-if="node.kind === 'protocol' && Object.keys(node.initial_values).length" class="mt-3">
            <strong>{{ node.title }} · {{ $t("page.workflowDefinitions.initialValues") }}</strong>
            <pre class="workflow-initial-values" tabindex="0">{{ JSON.stringify(node.initial_values, null, 2) }}</pre>
          </div>
        </template>
        <n-alert v-for="warning in savePreview.warnings" :key="warning" type="warning" class="mt-3">
          {{ warning }}
        </n-alert>
      </template>
      <template #footer>
        <div class="flex flex-wrap justify-end gap-2">
          <n-button :disabled="busy || confirmationUncertain" @click="saveVisible = false">
            {{ $t("page.workflowDefinitions.backToEdit") }}
          </n-button>
          <n-button type="primary" :loading="busy" :disabled="!savePreview" data-testid="workflow-confirm-save" @click="confirmSave">
            {{ $t("page.workflowDefinitions.confirmSave") }}
          </n-button>
        </div>
      </template>
    </n-modal>

    <n-modal v-model:show="runVisible" preset="card" class="aira-dialog" style="--aira-dialog-width: 44rem" :title="$t('page.workflowDefinitions.prepareRun')" :mask-closable="false" :closable="!busy && !confirmationUncertain" :close-on-esc="!busy && !confirmationUncertain">
      <n-alert type="info" class="mb-4">
        {{ $t("page.workflowDefinitions.runGovernance") }}
      </n-alert>
      <n-alert v-if="error" type="error" class="mb-4">
        {{ error }}
      </n-alert>
      <n-alert v-if="confirmationUncertain" type="warning" class="mb-4">
        {{ $t("page.workflowDefinitions.confirmationUncertain") }}
      </n-alert>
      <n-form-item :label="$t('page.workflowDefinitions.researchTask')" label-placement="top">
        <n-select v-model:value="taskId" :options="taskOptions" :disabled="busy || !!runPreview" :placeholder="$t('page.workflowDefinitions.selectTask')" data-testid="workflow-task" />
      </n-form-item>
      <section v-if="computeNodes.length && !runPreview" class="mb-4">
        <p class="aira-type-meta">
          {{ $t('page.workflowAnalysis.runComputeGovernance') }}
        </p>
        <n-form-item v-for="node in computeNodes" :key="node.node_id" :label="`${node.title} · ${$t('page.analysis.compute.approver')}`" label-placement="top">
          <n-select :value="computeApprovers[node.node_id] || null" :options="computeApproverOptions" clearable :disabled="busy" :placeholder="$t('page.workflowAnalysis.taskOwnerApprover')" :data-testid="`workflow-compute-approver-${node.node_id}`" @update:value="value => setComputeApprover(node.node_id, value)" />
        </n-form-item>
      </section>
      <n-alert v-if="!taskOptions.some(option => !option.disabled)" type="warning" class="mb-4">
        {{ $t("page.workflowDefinitions.noCompatibleTask") }}
      </n-alert>
      <n-button v-if="!runPreview" class="mb-4" :disabled="busy" @click="openResearch">
        {{ $t("page.workflowDefinitions.configureTask") }}
      </n-button>
      <template v-if="runPreview">
        <h3 class="aira-type-card-title">
          {{ taskTitle(runPreview.task_id) }}
        </h3>
        <p>{{ $t("page.workflowDefinitions.runImpact", { count: runPreview.nodes.length }) }}</p>
        <dl class="workflow-run-contract" data-testid="workflow-run-contract">
          <dt>{{ $t("page.workflowDefinitions.owner") }}</dt>
          <dd>{{ runPreview.owner?.name || runPreview.owner?.username || runPreview.owner?.id || "—" }}</dd>
          <dt>{{ $t("page.workflowDefinitions.budget") }}</dt>
          <dd>{{ runPreview.environment.operational_limits?.budget_limit === null || runPreview.environment.operational_limits?.budget_limit === undefined ? $t("page.workflowDefinitions.notSet") : `${runPreview.environment.operational_limits.budget_limit} ${runPreview.environment.operational_limits.budget_currency ?? ''}` }}</dd>
          <dt>{{ $t("page.workflowDefinitions.deadline") }}</dt>
          <dd>{{ runPreview.environment.operational_limits?.deadline_at || $t("page.workflowDefinitions.notSet") }}</dd>
        </dl>
        <section v-for="(governance, nodeId) in runPreview.compute_governance" :key="nodeId" class="workflow-node-settings my-3" data-testid="workflow-compute-governance">
          <h4 class="aira-type-label">
            {{ nodeTitle(nodeId) }} · {{ $t('page.workflowAnalysis.computeGovernance') }}
          </h4>
          <dl class="workflow-run-contract">
            <dt>{{ $t('page.analysis.compute.approver') }}</dt><dd>{{ approverName(governance.approver_user_id) }}</dd>
            <dt>{{ $t('page.analysis.compute.maxCost') }}</dt><dd>{{ governance.max_cost === null ? $t('page.workflowDefinitions.notSet') : `${governance.max_cost} ${governance.budget_currency || ''}` }}</dd>
            <dt>{{ $t('page.analysis.compute.deadline') }}</dt><dd>{{ governance.deadline_at || $t('page.workflowDefinitions.notSet') }}</dd>
          </dl>
        </section>
        <details class="workflow-environment" data-testid="workflow-run-environment">
          <summary>{{ $t("page.workflowDefinitions.environmentDetails") }}</summary>
          <pre class="workflow-initial-values" tabindex="0">{{ JSON.stringify(runPreview.environment, null, 2) }}</pre>
        </details>
        <ol class="workflow-preview-pins">
          <li v-for="pin in runPreview.pins" :key="pin.node_id">
            <strong>{{ graph.nodes.find(node => node.node_id === pin.node_id)?.title }}</strong>
            <span>{{ pin.name }} · {{ pin.kind === 'analysis' ? `${pin.engine_version} · ${pin.content_digest}` : pin.version }}</span>
          </li>
        </ol>
        <workflow-data-summary :graph="{ nodes: runPreview.nodes, edges: runPreview.edges ?? [], bindings: runPreview.bindings ?? [] }" :methods="context?.analysis_methods" :field-catalog="fieldCatalog" />
        <template v-for="node in runPreview.nodes" :key="node.node_id">
          <div v-if="node.kind === 'protocol' && Object.keys(node.initial_values).length" class="mt-3">
            <strong>{{ node.title }} · {{ $t("page.workflowDefinitions.initialValues") }}</strong>
            <pre class="workflow-initial-values" tabindex="0">{{ JSON.stringify(node.initial_values, null, 2) }}</pre>
          </div>
        </template>
      </template>
      <template #footer>
        <div class="flex flex-wrap justify-end gap-2">
          <n-button :disabled="busy || confirmationUncertain" @click="runPreview ? runPreview = null : runVisible = false">
            {{ runPreview ? $t("page.workflowDefinitions.backToEdit") : $t("common.cancel") }}
          </n-button>
          <n-button v-if="!runPreview" type="primary" :loading="busy" :disabled="!selectedTask" data-testid="workflow-preview-run" @click="previewRun">
            {{ $t("page.workflowDefinitions.previewRun") }}
          </n-button>
          <n-button v-else type="primary" :loading="busy" data-testid="workflow-confirm-run" @click="confirmRun">
            {{ $t("page.workflowDefinitions.confirmRun") }}
          </n-button>
        </div>
      </template>
    </n-modal>
  </div>
  <workflow-conversion-modal v-if="projectInfo" v-model:show="conversionVisible" :project-id="projectInfo.id" :project-name="projectInfo.name" @busy="value => busy = value" @created="conversionCreated" @open="openConverted" />
</template>

<script setup lang="ts">
import type { WorkflowAnalysisOutput, WorkflowAnalysisPublication, WorkflowComputeFileOutput, WorkflowComputeOutput } from "@/service/api/workflow-analysis-methods"
import type { WorkflowConversionResult } from "@/service/api/workflow-conversions"
import type { WorkflowAnalysisNode, WorkflowCondition, WorkflowContext, WorkflowDefinition, WorkflowDefinitionDetail, WorkflowField, WorkflowGraph, WorkflowNode, WorkflowProtocolNode, WorkflowRunPreview, WorkflowRunRequest, WorkflowSavePreview, WorkflowSaveRequest, WorkflowScalarBinding } from "@/service/api/workflow-definitions"
import { previewWorkflowAnalysisOutputs } from "@/service/api/workflow-analysis-methods"
import { confirmWorkflowDefinition, confirmWorkflowRun, fetchWorkflowContext, fetchWorkflowDefinition, fetchWorkflowDefinitions, previewWorkflowDefinition, previewWorkflowRun } from "@/service/api/workflow-definitions"
import { isComputeAnalysisRecipe } from "@/utils/analysis-compute"
import { createWorkflowAnalysisNode, createWorkflowId, duplicateWorkflowNode, emptyWorkflowGraph, moveWorkflowNode, normalizeWorkflowGraph, removeWorkflowNode, taskSupportsWorkflow, workflowAnalysisOutputKey, workflowAnalysisProblem, workflowConditionText, workflowDataProblem, workflowFields, workflowGraphProblem, workflowScalarFields } from "@/utils/workflow-editor"
import AnalysisMethodPublishModal from "@/views/analysis/components/analysis-method-publish-modal.vue"
import { useProjectInfoStore } from "@/views/project-protocols/hooks/useProjectInfoStore"
import dagre from "@dagrejs/dagre"
import { useMediaQuery } from "@vueuse/core"
import { useDialog } from "naive-ui"
import { computed, onBeforeUnmount, ref, watch } from "vue"
import { useI18n } from "vue-i18n"
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRouter } from "vue-router"
import WorkflowAnalysisInputs from "./components/workflow-analysis-inputs.vue"
import WorkflowCanvas from "./components/workflow-canvas.vue"
import WorkflowConversionModal from "./components/workflow-conversion-modal.vue"
import WorkflowDataSummary from "./components/workflow-data-summary.vue"
import WorkflowEdgeCondition from "./components/workflow-edge-condition.vue"
import WorkflowNodeBindings from "./components/workflow-node-bindings.vue"

const { t } = useI18n()
const router = useRouter()
const dialog = useDialog()
const { projectInfo } = useProjectInfoStore()
const narrow = useMediaQuery("(max-width: 767px)")
const viewMode = ref<"canvas" | "list">("canvas")
const effectiveView = computed(() => narrow.value ? "list" : viewMode.value)
const context = ref<WorkflowContext | null>(null)
const conversionVisible = ref(false)
const definitions = ref<WorkflowDefinition[]>([])
const detail = ref<WorkflowDefinitionDetail | null>(null)
const revisionId = ref<string | null>(null)
const title = ref("")
const description = ref("")
const graph = ref<WorkflowGraph>(emptyWorkflowGraph())
const baseline = ref("")
const selectedNodeId = ref<string | null>(null)
const addProtocolId = ref<string | null>(null)
const addKind = ref<"protocol" | "analysis">("protocol")
const addMethodId = ref<string | null>(null)
const publishMethodVisible = ref(false)
const outputCatalogs = ref<Record<string, { key: string, fields: WorkflowField[], error?: string, pending?: boolean }>>({})
const loading = ref(false)
const busy = ref(false)
const error = ref("")
const notice = ref("")
const saveVisible = ref(false)
const savePreview = ref<WorkflowSavePreview | null>(null)
const saveRequest = ref<WorkflowSaveRequest | null>(null)
const saveKey = ref("")
const runVisible = ref(false)
const runPreview = ref<WorkflowRunPreview | null>(null)
const runRequest = ref<WorkflowRunRequest | null>(null)
const runKey = ref("")
const confirmationUncertain = ref(false)
const taskId = ref<string | null>(null)
const computeApprovers = ref<Record<string, string>>({})
const computeNodes = computed(() => graph.value.nodes.filter(node => node.kind === "analysis" && node.analysis_kind === "compute"))
const computeApproverOptions = computed(() => (context.value?.compute_approvers ?? []).map(user => ({ label: user.name || user.username || user.id, value: user.id })))
let loadSequence = 0

const fingerprint = computed(() => JSON.stringify({ title: title.value, description: description.value, graph: graph.value }))
const dirty = computed(() => !!baseline.value && fingerprint.value !== baseline.value)
const editable = computed(() => !!context.value?.capabilities.write && !busy.value && !loading.value && !saveVisible.value && !runVisible.value && !publishMethodVisible.value)
const selectedNode = computed(() => graph.value.nodes.find(node => node.node_id === selectedNodeId.value))
const analysisFields = computed(() => Object.fromEntries(graph.value.nodes.filter((node): node is WorkflowAnalysisNode => node.kind === "analysis").map(node => [node.node_id, outputCatalogs.value[node.node_id]?.key === workflowAnalysisOutputKey(node) ? outputCatalogs.value[node.node_id].fields : []])))
const fieldCatalog = computed(() => Object.fromEntries(graph.value.nodes.map(node => [node.node_id, fieldsForNode(node.node_id)])))
const graphProblem = computed(() => workflowGraphProblem(graph.value) ?? workflowAnalysisProblem(graph.value, context.value?.analysis_methods ?? []) ?? (graph.value.nodes.some(node => node.kind === "analysis" && (outputCatalogs.value[node.node_id]?.key !== workflowAnalysisOutputKey(node) || outputCatalogs.value[node.node_id]?.pending || outputCatalogs.value[node.node_id]?.error)) ? "invalidAnalysis" : null) ?? workflowDataProblem(graph.value, context.value?.protocols ?? [], analysisFields.value))
const protocolOptions = computed(() => (context.value?.protocols ?? []).map(protocol => ({ label: protocol.name, value: protocol.id, disabled: !protocol.versions.length })))
const methodOptions = computed(() => (context.value?.analysis_methods ?? []).map(method => ({ label: `${method.title} · ${method.digest.slice(0, 8)}`, value: method.id })))
const revisionOptions = computed(() => (detail.value?.revisions ?? []).map(revision => ({ label: t("page.workflowDefinitions.revision", { number: revision.revision }), value: revision.id })))
const dependencyOptions = computed(() => graph.value.nodes.filter(node => node.node_id !== selectedNodeId.value).map(node => ({ label: `${graph.value.nodes.indexOf(node) + 1}. ${node.title}`, value: node.node_id })))
const taskOptions = computed(() => (context.value?.tasks ?? []).map(task => ({ label: task.title, value: task.id, disabled: !taskSupportsWorkflow(task, graph.value, context.value?.analysis_methods) })))
const selectedTask = computed(() => context.value?.tasks.find(task => task.id === taskId.value && taskSupportsWorkflow(task, graph.value, context.value?.analysis_methods)))

function errorText(cause: unknown) {
  const detail = (cause as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof detail === "string" ? detail : t("page.workflowDefinitions.requestFailed")
}
function uncertainResponse(cause: unknown) {
  const status = (cause as { response?: { status?: number } })?.response?.status
  return !status || status >= 500 || status === 408
}
function protocolName(id: string) {
  return context.value?.protocols.find(protocol => protocol.id === id)?.name ?? id
}
function analysisMethod(id: string) {
  return context.value?.analysis_methods?.find(method => method.id === id)
}
function cardResourceLabel(node: WorkflowNode) {
  if (node.kind === "protocol")
    return `${protocolName(node.protocol_id)} · ${versionLabel(node)}`
  const method = analysisMethod(node.method_publication_id)
  const runtime = method && isComputeAnalysisRecipe(method.recipe) ? `${method.recipe.language === "python" ? "Python" : "R"} · ${method.compute_contract?.environment.name ?? "—"} r${method.compute_contract?.environment.metadata.environment_revision ?? "—"} · ` : ""
  return `${t("page.workflowAnalysis.analysisCard")} · ${runtime}${method?.title ?? node.method_publication_id} · ${method?.digest.slice(0, 8) ?? "—"}`
}
function methodPublished(method: WorkflowAnalysisPublication) {
  if (!context.value || method.project_id !== projectInfo.value?.id)
    return
  context.value.analysis_methods = [method, ...(context.value.analysis_methods ?? []).filter(item => item.id !== method.id)]
  addMethodId.value = method.id
  notice.value = t("page.workflowAnalysis.analysisReady")
}
function approverName(id: string) {
  const user = context.value?.compute_approvers?.find(user => user.id === id)
  return user?.name || user?.username || id
}
function setComputeApprover(nodeId: string, id: string | null) {
  if (id)
    computeApprovers.value[nodeId] = id
  else
    delete computeApprovers.value[nodeId]
}
function selectAnalysisMethod(id: string) {
  const node = selectedNode.value
  const method = analysisMethod(id)
  if (!editable.value || node?.kind !== "analysis" || !method || node.method_publication_id === id)
    return
  const replacement = createWorkflowAnalysisNode(method, node.node_id, node.position)
  replacement.title = node.title
  replacement.record_sources = node.record_sources
  graph.value.nodes = graph.value.nodes.map(item => item.node_id === node.node_id ? replacement : item)
  if (replacement.analysis_kind === "compute" && graph.value.schema_version < 3)
    graph.value.schema_version = 3
}
function updateBuiltinOutputs(outputs: WorkflowAnalysisOutput[]) {
  if (selectedNode.value?.kind === "analysis" && selectedNode.value.analysis_kind !== "compute")
    selectedNode.value.analysis_outputs = outputs
}
function updateComputeOutputs(outputs: WorkflowComputeOutput[]) {
  if (selectedNode.value?.kind === "analysis" && selectedNode.value.analysis_kind === "compute")
    selectedNode.value.compute_outputs = outputs
}
function updateComputeFiles(outputs: WorkflowComputeFileOutput[]) {
  if (selectedNode.value?.kind === "analysis" && selectedNode.value.analysis_kind === "compute") {
    selectedNode.value.compute_file_outputs = outputs
    if (outputs.length)
      graph.value.schema_version = 4
  }
}
function updateBindings(bindings: WorkflowScalarBinding[]) {
  graph.value.bindings = bindings
  if (bindings.some(binding => binding.value_type === "file"))
    graph.value.schema_version = 4
}
function versionLabel(node: WorkflowProtocolNode) {
  return context.value?.protocols.find(protocol => protocol.id === node.protocol_id)?.versions.find(version => version.id === node.protocol_version_id)?.version ?? node.protocol_version_id
}
function versionOptions(node: WorkflowProtocolNode) {
  const versions = context.value?.protocols.find(protocol => protocol.id === node.protocol_id)?.versions ?? []
  const options = versions.map(version => ({ label: version.version, value: version.id }))
  if (!versions.some(version => version.id === node.protocol_version_id))
    options.push({ label: node.protocol_version_id, value: node.protocol_version_id })
  return options
}
function taskTitle(id: string) {
  return context.value?.tasks.find(task => task.id === id)?.title ?? t("page.workflowDefinitions.savedRun")
}
function runStatus(status: string) {
  const key = `page.research.runStatus.${status}`
  const text = t(key)
  return text === key ? status : text
}
function actionStatus(status: string, skipReason?: string | null) {
  if (skipReason === "branch_not_selected")
    return t("page.workflowDefinitions.conditions.branchNotSelected")
  if (skipReason === "dependency_failed")
    return t("page.workflowDefinitions.conditions.dependencyFailed")
  const key = `page.research.actionStatus.${status}`
  const text = t(key)
  return text === key ? status : text
}
function nodeTitle(id: string) {
  return graph.value.nodes.find(node => node.node_id === id)?.title ?? id
}
function fieldsForNode(id: string) {
  return workflowFields(graph.value.nodes.find(node => node.node_id === id), context.value?.protocols ?? [], analysisFields.value)
}
function incomingEdges(nodeId: string) {
  return graph.value.edges.filter(edge => edge.target_node_id === nodeId)
}
function incomingIds(nodeId: string) {
  return graph.value.edges.filter(edge => edge.target_node_id === nodeId).map(edge => edge.source_node_id)
}
function incomingTitles(nodeId: string) {
  return incomingEdges(nodeId).map(edge => `${nodeTitle(edge.source_node_id)}${edge.condition ? ` (${workflowConditionText(edge.condition)})` : ""}`).join(" · ") || t("page.workflowDefinitions.startIndependently")
}
async function confirmDiscard() {
  if (!dirty.value)
    return true
  return new Promise<boolean>((resolve) => {
    dialog.warning({
      title: t("page.workflowDefinitions.unsaved"),
      content: t("page.workflowDefinitions.discardHint"),
      positiveText: t("page.workflowDefinitions.discard"),
      negativeText: t("common.cancel"),
      onPositiveClick: () => resolve(true),
      onNegativeClick: () => resolve(false),
      onClose: () => resolve(false),
      onMaskClick: () => resolve(false),
    })
  })
}
function resetEditor() {
  detail.value = null
  revisionId.value = null
  title.value = ""
  description.value = ""
  graph.value = emptyWorkflowGraph()
  outputCatalogs.value = {}
  selectedNodeId.value = null
  baseline.value = fingerprint.value
  saveVisible.value = false
  runVisible.value = false
  savePreview.value = null
  runPreview.value = null
  confirmationUncertain.value = false
}
async function startNew() {
  if (!busy.value && await confirmDiscard()) {
    resetEditor()
    notice.value = ""
    error.value = ""
  }
}
async function openConversion() {
  if (!busy.value && await confirmDiscard()) {
    resetEditor()
    conversionVisible.value = true
  }
}
function conversionCreated(result: WorkflowConversionResult) {
  definitions.value = [result, ...definitions.value.filter(item => item.id !== result.id)]
}
async function openConverted(result: WorkflowConversionResult) {
  conversionVisible.value = false
  await openDefinition(result.id)
  if (detail.value?.id === result.id)
    applyRevision(result.confirmed_revision_id)
}
function applyRevision(id: string | null) {
  const revision = detail.value?.revisions.find(revision => revision.id === id) ?? detail.value?.current_revision
  revisionId.value = revision?.id ?? null
  title.value = revision?.title ?? detail.value?.title ?? ""
  description.value = revision?.description ?? detail.value?.description ?? ""
  graph.value = revision ? normalizeWorkflowGraph(revision.graph) : emptyWorkflowGraph()
  selectedNodeId.value = null
  baseline.value = fingerprint.value
}
async function selectRevision(id: string) {
  if (await confirmDiscard())
    applyRevision(id)
}
async function openDefinition(id: string) {
  if (busy.value || !await confirmDiscard())
    return
  const sequence = ++loadSequence
  loading.value = true
  error.value = ""
  notice.value = ""
  try {
    const loaded = await fetchWorkflowDefinition(id)
    if (sequence !== loadSequence)
      return
    detail.value = loaded
    applyRevision(loaded.current_revision?.id ?? null)
  }
  catch (cause) {
    if (sequence === loadSequence)
      error.value = errorText(cause)
  }
  finally {
    if (sequence === loadSequence)
      loading.value = false
  }
}
async function loadWorkspace() {
  const projectId = projectInfo.value?.id
  const sequence = ++loadSequence
  if (!projectId)
    return
  loading.value = true
  error.value = ""
  try {
    const [list, nextContext] = await Promise.all([fetchWorkflowDefinitions(projectId), fetchWorkflowContext(projectId)])
    if (sequence !== loadSequence)
      return
    definitions.value = list.items
    context.value = nextContext
    if (nextContext.protocols.length === 1)
      addProtocolId.value = nextContext.protocols[0].id
    if (detail.value) {
      const loaded = await fetchWorkflowDefinition(detail.value.id)
      if (sequence !== loadSequence)
        return
      detail.value = loaded
      applyRevision(revisionId.value)
    }
  }
  catch (cause) {
    if (sequence === loadSequence) {
      context.value = null
      error.value = errorText(cause)
    }
  }
  finally {
    if (sequence === loadSequence)
      loading.value = false
  }
}
async function refresh() {
  if (!busy.value && await confirmDiscard()) {
    if (!detail.value)
      resetEditor()
    await loadWorkspace()
  }
}
function addCard() {
  const protocol = context.value?.protocols.find(protocol => protocol.id === addProtocolId.value)
  if (!editable.value || !protocol?.versions.length)
    return
  const id = `node_${createWorkflowId()}`
  graph.value.nodes.push({ node_id: id, kind: "protocol", protocol_id: protocol.id, protocol_version_id: protocol.versions[0].id, title: protocol.name, position: { x: 40 + graph.value.nodes.length % 3 * 310, y: 40 + Math.floor(graph.value.nodes.length / 3) * 150 }, initial_values: {} })
  selectedNodeId.value = id
}
function addAnalysisCard() {
  const method = context.value?.analysis_methods?.find(method => method.id === addMethodId.value)
  if (!editable.value || !method)
    return
  const id = `node_${createWorkflowId()}`
  if (graph.value.schema_version < (isComputeAnalysisRecipe(method.recipe) ? 3 : 2))
    graph.value.schema_version = isComputeAnalysisRecipe(method.recipe) ? 3 : 2
  graph.value.nodes.push(createWorkflowAnalysisNode(method, id, { x: 40 + graph.value.nodes.length % 3 * 310, y: 40 + Math.floor(graph.value.nodes.length / 3) * 150 }))
  selectedNodeId.value = id
}
function duplicateCard(node: WorkflowNode) {
  const copy = duplicateWorkflowNode(JSON.parse(JSON.stringify(node)), `node_${createWorkflowId()}`)
  graph.value.nodes.push(copy)
  selectedNodeId.value = copy.node_id
}
function removeCard(id: string) {
  graph.value = removeWorkflowNode(graph.value, id)
  if (selectedNodeId.value === id)
    selectedNodeId.value = null
}
function moveCard(id: string, offset: -1 | 1) {
  graph.value = moveWorkflowNode(graph.value, id, offset)
}
function connectCards(source: string, target: string) {
  if (!editable.value)
    return
  const next = { ...graph.value, edges: [...graph.value.edges, { edge_id: `edge_${createWorkflowId()}`, source_node_id: source, target_node_id: target, condition: null }] }
  const problem = workflowGraphProblem(next)
  if (problem) {
    error.value = t(`page.workflowDefinitions.validation.${problem}`)
    return
  }
  graph.value = next
  error.value = ""
}
function setDependencies(ids: string[]) {
  const node = selectedNode.value
  if (!node || !editable.value)
    return
  const oldEdges = graph.value.edges.filter(edge => edge.target_node_id === node.node_id)
  const next = { ...graph.value, edges: [...graph.value.edges.filter(edge => edge.target_node_id !== node.node_id), ...ids.map(id => oldEdges.find(edge => edge.source_node_id === id) ?? { edge_id: `edge_${createWorkflowId()}`, source_node_id: id, target_node_id: node.node_id, condition: null })] }
  const problem = workflowGraphProblem(next)
  if (problem) {
    error.value = t(`page.workflowDefinitions.validation.${problem}`)
    return
  }
  next.bindings = next.bindings.filter(binding => binding.target_node_id !== node.node_id || ids.includes(binding.source_node_id))
  if (node.kind === "analysis")
    node.record_sources = node.record_sources.filter(source => ids.includes(source.source_node_id))
  graph.value = next
  error.value = ""
}
function updateCondition(edgeId: string, condition: WorkflowCondition | null) {
  if (!editable.value)
    return
  const edge = graph.value.edges.find(edge => edge.edge_id === edgeId)
  if (edge)
    edge.condition = condition
}
function updatePositions(nodes: Array<{ node_id: string, position: { x: number, y: number } }>) {
  if (!editable.value)
    return
  for (const change of nodes) {
    const node = graph.value.nodes.find(node => node.node_id === change.node_id)
    if (node)
      node.position = { x: change.position.x, y: change.position.y }
  }
}
function arrange() {
  const layout = new dagre.graphlib.Graph().setGraph({ rankdir: "LR", nodesep: 44, ranksep: 72 }).setDefaultEdgeLabel(() => ({}))
  graph.value.nodes.forEach(node => layout.setNode(node.node_id, { width: 274, height: 122 }))
  graph.value.edges.forEach(edge => layout.setEdge(edge.source_node_id, edge.target_node_id))
  dagre.layout(layout)
  updatePositions(graph.value.nodes.map(node => ({ node_id: node.node_id, position: { x: layout.node(node.node_id).x - 137, y: layout.node(node.node_id).y - 61 } })))
}
async function previewSave() {
  if (!projectInfo.value || !editable.value || graphProblem.value)
    return
  busy.value = true
  error.value = ""
  notice.value = ""
  try {
    saveRequest.value = { project_id: projectInfo.value.id, definition_id: detail.value?.id, expected_revision: detail.value?.revision, title: title.value.trim(), description: description.value.trim(), graph: JSON.parse(JSON.stringify(graph.value)) }
    savePreview.value = await previewWorkflowDefinition(saveRequest.value)
    saveKey.value = createWorkflowId()
    confirmationUncertain.value = false
    saveVisible.value = true
  }
  catch (cause) {
    error.value = errorText(cause)
  }
  finally {
    busy.value = false
  }
}
async function confirmSave() {
  if (!saveRequest.value || !savePreview.value || busy.value)
    return
  busy.value = true
  error.value = ""
  let confirmed = false
  try {
    const saved = await confirmWorkflowDefinition({ ...saveRequest.value, preview_digest: savePreview.value.preview_digest, idempotency_key: saveKey.value })
    confirmed = true
    // Preserve the idempotency key until the confirmed asset is loaded, including uncertain responses.
    const loaded = await fetchWorkflowDefinition(saved.id)
    const published = loaded.revisions.find(revision => revision.id === saved.confirmed_revision_id)
    if (!published)
      throw new Error("The confirmed Workflow revision could not be loaded")
    detail.value = loaded
    definitions.value = [saved, ...definitions.value.filter(item => item.id !== saved.id)]
    applyRevision(published.id)
    saveVisible.value = false
    confirmationUncertain.value = false
    notice.value = t("page.workflowDefinitions.savedResult", { title: published.title, revision: published.revision, project: projectInfo.value?.name })
  }
  catch (cause) {
    confirmationUncertain.value = confirmed || uncertainResponse(cause)
    error.value = errorText(cause)
  }
  finally {
    busy.value = false
  }
}
async function openRunDialog() {
  if (!detail.value || dirty.value || !projectInfo.value)
    return
  busy.value = true
  error.value = ""
  try {
    context.value = await fetchWorkflowContext(projectInfo.value.id)
    const compatible = context.value.tasks.filter(task => taskSupportsWorkflow(task, graph.value, context.value?.analysis_methods))
    taskId.value = compatible.length === 1 ? compatible[0].id : null
    computeApprovers.value = {}
    runPreview.value = null
    confirmationUncertain.value = false
    runVisible.value = true
  }
  catch (cause) {
    error.value = errorText(cause)
  }
  finally {
    busy.value = false
  }
}
async function previewRun() {
  if (!detail.value || !selectedTask.value || !revisionId.value || busy.value)
    return
  busy.value = true
  error.value = ""
  try {
    runRequest.value = { task_id: selectedTask.value.id, expected_task_revision: selectedTask.value.revision, workflow_revision_id: revisionId.value }
    if (computeNodes.value.length)
      runRequest.value.compute_approvers = Object.fromEntries(computeNodes.value.filter(node => computeApprovers.value[node.node_id]).map(node => [node.node_id, computeApprovers.value[node.node_id]]))
    runPreview.value = await previewWorkflowRun(detail.value.id, runRequest.value)
    runKey.value = createWorkflowId()
  }
  catch (cause) {
    error.value = errorText(cause)
  }
  finally {
    busy.value = false
  }
}
async function confirmRun() {
  if (!detail.value || !runRequest.value || !runPreview.value || busy.value)
    return
  busy.value = true
  error.value = ""
  try {
    const result = await confirmWorkflowRun(detail.value.id, { ...runRequest.value, preview_digest: runPreview.value.preview_digest, idempotency_key: runKey.value })
    runVisible.value = false
    confirmationUncertain.value = false
    notice.value = t("page.workflowDefinitions.runCreated")
    busy.value = false
    await router.push({ name: "research-task-detail", params: { taskId: result.task_id } })
  }
  catch (cause) {
    confirmationUncertain.value = uncertainResponse(cause)
    error.value = errorText(cause)
  }
  finally {
    busy.value = false
  }
}
async function openResearch() {
  runVisible.value = false
  await router.push({ name: "project-research" })
}
function beforeUnload(event: BeforeUnloadEvent) {
  if (dirty.value || busy.value || confirmationUncertain.value) {
    event.preventDefault()
    event.returnValue = ""
  }
}
async function loadOutputCatalog(node: WorkflowAnalysisNode) {
  const key = workflowAnalysisOutputKey(node)
  outputCatalogs.value[node.node_id] = { key, fields: [], pending: true }
  try {
    const response = await previewWorkflowAnalysisOutputs(node.method_publication_id, node.analysis_kind === "compute" ? node.compute_outputs : node.analysis_outputs, node.analysis_kind === "compute" ? node.compute_file_outputs : undefined)
    if (outputCatalogs.value[node.node_id]?.key === key)
      outputCatalogs.value[node.node_id] = { key, fields: response.fields }
  }
  catch (cause) {
    if (outputCatalogs.value[node.node_id]?.key === key)
      outputCatalogs.value[node.node_id] = { key, fields: [], error: errorText(cause) }
  }
}
window.addEventListener("beforeunload", beforeUnload)
onBeforeUnmount(() => {
  loadSequence++
  window.removeEventListener("beforeunload", beforeUnload)
})
onBeforeRouteLeave(async () => busy.value || confirmationUncertain.value ? false : confirmDiscard())
onBeforeRouteUpdate(async () => busy.value || confirmationUncertain.value ? false : confirmDiscard())
watch(() => graph.value.nodes.filter((node): node is WorkflowAnalysisNode => node.kind === "analysis").map(node => ({ node, key: workflowAnalysisOutputKey(node) })), (nodes) => {
  for (const { node, key } of nodes) {
    if (outputCatalogs.value[node.node_id]?.key === key)
      continue
    void loadOutputCatalog(node)
  }
}, { immediate: true })
watch(() => projectInfo.value?.id, () => {
  resetEditor()
  context.value = null
  definitions.value = []
  addProtocolId.value = null
  void loadWorkspace()
}, { immediate: true })
</script>

<style scoped>
.workflow-page { min-width: 0; }
.workflow-workspace { display: grid; grid-template-columns: minmax(220px, 270px) minmax(0, 1fr); gap: 24px; align-items: start; }
.workflow-panel { min-width: 0; padding: 24px; border: 1px solid #e5e7eb; border-radius: 14px; background: white; }
.workflow-library { padding: 18px; }
.workflow-definition-list { display: flex; flex-direction: column; gap: 8px; }
.workflow-library-item { display: flex; flex-direction: column; gap: 6px; width: 100%; padding: 12px; border: 1px solid #e5e7eb; border-radius: 8px; background: white; text-align: start; overflow-wrap: anywhere; cursor: pointer; }
.workflow-library-item--selected { border-color: #0084e2; background: #eff8ff; }
.workflow-library-item:focus-visible { outline: 2px solid #0084e2; outline-offset: 2px; }
.workflow-add-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 12px; }
.workflow-revision-select { max-width: 240px; }
.workflow-cards { display: grid; gap: 14px; }
.workflow-card, .workflow-node-settings { min-width: 0; padding: 18px; border: 1px solid #e2e8f0; border-radius: 10px; overflow-wrap: anywhere; }
.workflow-node-settings { background: #f8fafc; }
.workflow-run-row { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px; padding: 14px 0; border-top: 1px solid #e5e7eb; }
.workflow-run-actions { flex-basis: 100%; margin: 0; padding-inline-start: 20px; overflow-wrap: anywhere; }
.workflow-run-actions li { margin-top: 6px; }
.workflow-preview-pins { padding-inline-start: 24px; }
.workflow-preview-pins li { padding: 10px 0; overflow-wrap: anywhere; }
.workflow-preview-pins strong, .workflow-preview-pins span { display: block; }
.workflow-initial-values { max-height: 240px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; padding: 12px; border: 1px solid #e2e8f0; border-radius: 8px; font-size: 13px; line-height: 1.6; background: #f8fafc; }
.workflow-run-contract { display: grid; grid-template-columns: auto minmax(0, 1fr); column-gap: 16px; row-gap: 8px; overflow-wrap: anywhere; }
.workflow-run-contract dt { font-weight: 600; }
.workflow-run-contract dd { margin: 0; }
.workflow-environment { margin: 16px 0; overflow-wrap: anywhere; }
.workflow-environment summary { cursor: pointer; }
@media (max-width: 1100px) { .workflow-workspace { grid-template-columns: minmax(0, 1fr); } .workflow-definition-list { max-height: 210px; overflow-y: auto; } }
@media (max-width: 767px) { .workflow-panel { padding: 16px; } .workflow-add-row { grid-template-columns: minmax(0, 1fr); } .workflow-card, .workflow-node-settings { padding: 14px; } .workflow-page :deep(.n-form-item-label) { white-space: normal; } }
</style>

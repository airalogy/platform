<template>
  <section class="research-assets-panel">
    <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <div class="aira-type-eyebrow">
          {{ $t("page.research.scientificAssets") }}
        </div>
        <h2 class="aira-type-section-title mb-0 mt-1">
          {{ $t("page.research.resultsAndEvidence") }}
        </h2>
        <p class="aira-type-meta aira-text-secondary mb-0 mt-2">
          {{ $t("page.research.scientificAssetsHint") }}
        </p>
      </div>
      <div class="flex flex-wrap gap-2">
        <n-button size="small" secondary @click="openModal('asset')">
          {{ $t("page.research.addDataAsset") }}
        </n-button>
        <n-button size="small" secondary @click="openModal('evidence')">
          {{ $t("page.research.addEvidence") }}
        </n-button>
        <n-button size="small" type="primary" @click="openModal('claim')">
          {{ $t("page.research.addClaim") }}
        </n-button>
        <n-button
          size="small"
          type="primary"
          secondary
          :disabled="!knowledgeEvidenceOptions.length"
          @click="openModal('knowledge')"
        >
          {{ $t("page.research.suggestKnowledge") }}
        </n-button>
        <n-button
          size="small"
          type="warning"
          secondary
          :disabled="!knowledgeEvidenceOptions.length || !protocolOptions.length"
          @click="openModal('protocolImprovement')"
        >
          {{ $t("page.research.proposeProtocolImprovement") }}
        </n-button>
      </div>
    </div>

    <n-spin :show="loading" class="mt-4 min-h-20">
      <n-alert v-if="loadError" type="error" :title="$t('page.research.assetsLoadError')">
        <n-button size="tiny" class="mt-2" @click="loadAssets">
          {{ $t("common.retry") }}
        </n-button>
      </n-alert>
      <n-empty
        v-else-if="isEmpty"
        class="py-6"
        :description="$t('page.research.noScientificAssets')"
      />
      <n-tabs v-else type="line" animated>
        <n-tab-pane name="claims" :tab="`${$t('page.research.claims')} (${bundle.claims.length})`">
          <div class="space-y-3">
            <article v-for="claim in bundle.claims" :key="claim.id" class="scientific-card">
              <div class="flex flex-wrap items-start justify-between gap-2">
                <div class="min-w-0 flex-1">
                  <div class="flex flex-wrap items-center gap-2">
                    <n-tag size="small" round :type="claimStateType(claim.state)">
                      {{ claimStateLabel(claim.state) }}
                    </n-tag>
                    <n-tag v-if="claim.generated_by === 'aira_assisted'" size="small" round type="info">
                      {{ $t("page.research.airaAssisted") }}
                    </n-tag>
                    <span class="aira-type-meta">r{{ claim.revision }}</span>
                    <span v-if="claim.confidence != null" class="aira-type-meta">
                      {{ $t("page.research.confidence") }} {{ Math.round(claim.confidence * 100) }}%
                    </span>
                  </div>
                  <p class="aira-type-body mb-0 mt-2 whitespace-pre-wrap">
                    {{ claim.statement }}
                  </p>
                  <p v-if="claim.uncertainty" class="aira-type-meta aira-text-secondary mb-0 mt-2 whitespace-pre-wrap">
                    {{ $t("page.research.uncertainty") }} · {{ claim.uncertainty }}
                  </p>
                  <div v-if="claim.evidence.length" class="aira-type-meta mt-2">
                    {{ $t("page.research.linkedEvidenceCount", { count: claim.evidence.length }) }}
                  </div>
                  <div v-if="claim.evidence.length" class="mt-2 space-y-2">
                    <div v-for="relation in claim.evidence" :key="relation.evidence_id" class="claim-evidence-row">
                      <div class="flex flex-wrap items-center gap-2">
                        <n-tag size="tiny" round :type="claimRelationType(relation.relation)">
                          {{ claimRelationLabel(relation.relation) }}
                        </n-tag>
                        <span class="aira-type-meta break-all">
                          {{ evidenceLabelById(relation.evidence_id) }}
                        </span>
                      </div>
                      <p v-if="relation.rationale" class="aira-type-meta aira-text-secondary mb-0 mt-1 whitespace-pre-wrap">
                        {{ relation.rationale }}
                      </p>
                    </div>
                  </div>
                </div>
                <div v-if="claim.state === 'draft' || claim.state === 'suggested'" class="flex gap-1">
                  <n-button size="tiny" type="success" secondary @click="confirmClaimReview(claim, 'reviewed')">
                    {{ $t("page.research.acceptClaim") }}
                  </n-button>
                  <n-button size="tiny" type="error" tertiary @click="confirmClaimReview(claim, 'rejected')">
                    {{ $t("common.reject") }}
                  </n-button>
                </div>
              </div>
            </article>
            <n-empty v-if="!bundle.claims.length" class="py-5" :description="$t('page.research.noClaims')" />
          </div>
        </n-tab-pane>

        <n-tab-pane name="evidence" :tab="`${$t('page.research.evidence')} (${bundle.evidence.length})`">
          <div class="space-y-3">
            <article v-for="item in bundle.evidence" :key="item.id" class="scientific-card">
              <div class="flex flex-wrap items-start justify-between gap-2">
                <div class="min-w-0 flex-1">
                  <div class="flex flex-wrap items-center gap-2">
                    <n-tag size="small" round :type="evidenceStateType(item.quality_state)">
                      {{ evidenceStateLabel(item.quality_state) }}
                    </n-tag>
                    <span class="aira-type-meta">{{ evidenceKindLabel(item.kind) }}</span>
                    <span class="aira-type-meta">{{ artifactTypeLabel(item.artifact_type) }}</span>
                  </div>
                  <p class="aira-type-body mb-0 mt-2">
                    {{ item.summary || artifactLabel(item) }}
                  </p>
                  <div class="aira-type-meta mt-1 break-all">
                    {{ artifactLabel(item) }}
                  </div>
                  <n-collapse v-if="item.artifact_snapshot" class="mt-3">
                    <n-collapse-item :title="$t('page.research.actionOutputSnapshot')" :name="item.id">
                      <div class="aira-type-meta break-all">
                        SHA-256 · {{ item.artifact_snapshot.digest }}
                      </div>
                      <pre class="action-output-json mt-2">{{ formatActionOutput(item.artifact_snapshot.output_data) }}</pre>
                    </n-collapse-item>
                  </n-collapse>
                </div>
                <div v-if="item.quality_state === 'pending'" class="flex gap-1">
                  <n-button size="tiny" type="success" secondary @click="confirmEvidenceReview(item, 'validated')">
                    {{ $t("page.research.validateEvidence") }}
                  </n-button>
                  <n-button size="tiny" type="error" tertiary @click="confirmEvidenceReview(item, 'rejected')">
                    {{ $t("common.reject") }}
                  </n-button>
                </div>
              </div>
            </article>
            <n-empty v-if="!bundle.evidence.length" class="py-5" :description="$t('page.research.noEvidence')" />
          </div>
        </n-tab-pane>

        <n-tab-pane name="knowledge" :tab="`${$t('page.research.knowledgeCandidates')} (${bundle.knowledge_items.length})`">
          <div class="space-y-3">
            <article v-for="item in bundle.knowledge_items" :key="item.id" class="scientific-card">
              <div class="flex flex-wrap items-center gap-2">
                <n-tag size="small" round :type="item.state === 'reviewed' ? 'success' : 'warning'">
                  {{ knowledgeStateLabel(item.state) }}
                </n-tag>
                <span class="aira-type-meta">{{ knowledgeKindLabel(item.kind) }} · r{{ item.revision }}</span>
              </div>
              <h3 class="aira-type-card-title mb-0 mt-2 break-words">
                {{ item.title }}
              </h3>
              <p class="aira-type-body line-clamp-3 mb-0 mt-2 whitespace-pre-wrap">
                {{ item.body }}
              </p>
              <div class="mt-3 flex flex-wrap items-center justify-between gap-2">
                <span class="aira-type-meta aira-text-secondary">
                  {{ $t("page.research.knowledgeEvidenceCount", { count: item.evidence.length }) }}
                </span>
                <n-button size="tiny" secondary @click="openProjectKnowledge">
                  {{ $t("page.research.openProjectKnowledge") }}
                </n-button>
              </div>
            </article>
            <n-empty v-if="!bundle.knowledge_items.length" class="py-5" :description="$t('page.research.noKnowledgeCandidates')" />
          </div>
        </n-tab-pane>

        <n-tab-pane name="protocol-improvements" :tab="`${$t('page.research.protocolImprovements')} (${bundle.protocol_improvements.length})`">
          <div class="space-y-3">
            <article v-for="proposal in bundle.protocol_improvements" :key="proposal.id" class="scientific-card">
              <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div class="min-w-0 flex-1">
                  <div class="flex flex-wrap items-center gap-2">
                    <n-tag size="small" round :type="protocolImprovementStateType(proposal.state)">
                      {{ protocolImprovementStateLabel(proposal.state) }}
                    </n-tag>
                    <n-tag v-if="proposal.generated_by === 'aira_assisted'" size="small" round type="info">
                      {{ $t("page.research.airaAssisted") }}
                    </n-tag>
                    <span class="aira-type-meta">
                      {{ proposal.protocol?.name || proposal.protocol_id }} · v{{ proposal.base_protocol_version }}
                    </span>
                    <span class="aira-type-meta">r{{ proposal.revision }}</span>
                  </div>
                  <h3 class="aira-type-card-title mb-0 mt-2 break-words">
                    {{ proposal.title }}
                  </h3>
                  <p class="aira-type-body aira-text-secondary mb-0 mt-2 whitespace-pre-wrap">
                    {{ proposal.rationale }}
                  </p>
                  <div class="scientific-change mt-3">
                    <div class="aira-type-eyebrow">
                      {{ $t("page.research.proposedChanges") }}
                    </div>
                    <p class="aira-type-body mb-0 mt-1 whitespace-pre-wrap">
                      {{ proposal.proposed_changes }}
                    </p>
                  </div>
                  <div class="aira-type-meta mt-3">
                    {{ $t("page.research.protocolImprovementEvidenceCount", { count: proposal.evidence.length }) }}
                    <template v-if="proposal.applied_protocol_version">
                      · {{ $t("page.research.appliedAsVersion", { version: proposal.applied_protocol_version }) }}
                    </template>
                  </div>
                </div>
                <div class="flex shrink-0 flex-wrap gap-1">
                  <template v-if="proposal.state === 'suggested'">
                    <n-button size="tiny" type="success" secondary @click="confirmProtocolImprovementReview(proposal, 'reviewed')">
                      {{ $t("page.research.acceptProtocolImprovement") }}
                    </n-button>
                    <n-button size="tiny" type="error" tertiary @click="confirmProtocolImprovementReview(proposal, 'rejected')">
                      {{ $t("common.reject") }}
                    </n-button>
                  </template>
                  <n-button v-else-if="proposal.state === 'reviewed'" size="tiny" type="primary" @click="openProtocolImprovementDraft(proposal)">
                    {{ $t("page.research.openProtocolVersionDraft") }}
                  </n-button>
                  <n-button v-else-if="proposal.state === 'applied'" size="tiny" secondary @click="openAppliedProtocol(proposal)">
                    {{ $t("page.research.openAppliedProtocol") }}
                  </n-button>
                </div>
              </div>
            </article>
            <n-empty v-if="!bundle.protocol_improvements.length" class="py-5" :description="$t('page.research.noProtocolImprovements')" />
          </div>
        </n-tab-pane>

        <n-tab-pane name="data" :tab="`${$t('page.research.dataAssets')} (${bundle.data_assets.length})`">
          <div class="grid grid-cols-1 gap-3 md:grid-cols-2">
            <article v-for="asset in bundle.data_assets" :key="asset.id" class="scientific-card">
              <div class="flex items-start justify-between gap-2">
                <div class="min-w-0">
                  <div class="flex flex-wrap items-center gap-2">
                    <n-tag size="small" round :type="asset.status === 'ready' ? 'success' : 'default'">
                      {{ dataAssetStatusLabel(asset.status) }}
                    </n-tag>
                    <span class="aira-type-meta">{{ dataAssetKindLabel(asset.kind) }} · v{{ asset.current_version }}</span>
                  </div>
                  <h3 class="aira-type-card-title mb-0 mt-2 break-words">
                    {{ asset.name }}
                  </h3>
                  <p v-if="asset.description" class="aira-type-meta aira-text-secondary line-clamp-2 mb-0 mt-1">
                    {{ asset.description }}
                  </p>
                  <a
                    v-if="currentVersion(asset)?.external_uri"
                    class="aira-type-meta mt-2 block truncate text-primary"
                    :href="currentVersion(asset)?.external_uri"
                    target="_blank"
                    rel="noopener noreferrer"
                  >{{ currentVersion(asset)?.external_uri }}</a>
                </div>
                <n-button
                  v-if="asset.status === 'draft'"
                  size="tiny"
                  type="success"
                  secondary
                  @click="confirmAssetReady(asset)"
                >
                  {{ $t("page.research.markReady") }}
                </n-button>
              </div>
            </article>
          </div>
          <n-empty v-if="!bundle.data_assets.length" class="py-5" :description="$t('page.research.noDataAssets')" />
        </n-tab-pane>
      </n-tabs>
    </n-spin>

    <n-modal
      style="--aira-dialog-width: 42rem"
      v-model:show="modalVisible"
      preset="card"
      class="aira-dialog research-asset-modal"
      :title="modalTitle"
      :mask-closable="false"
      @after-leave="resetModal"
    >
      <template v-if="!preview">
        <n-form v-if="modalKind === 'asset'" label-placement="top">
          <div class="grid grid-cols-1 gap-x-3 sm:grid-cols-2">
            <n-form-item :label="$t('page.research.assetName')" required>
              <n-input v-model:value="assetDraft.name" />
            </n-form-item>
            <n-form-item :label="$t('page.research.assetKind')" required>
              <n-select v-model:value="assetDraft.kind" :options="assetKindOptions" />
            </n-form-item>
          </div>
          <n-form-item :label="$t('page.research.externalUri')" required>
            <n-input v-model:value="assetDraft.external_uri" placeholder="https://…" />
          </n-form-item>
          <n-form-item :label="$t('page.research.mediaType')">
            <n-input v-model:value="assetDraft.media_type" placeholder="text/csv" />
          </n-form-item>
          <n-form-item :label="$t('common.description')">
            <n-input v-model:value="assetDraft.description" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" />
          </n-form-item>
        </n-form>

        <n-form v-else-if="modalKind === 'evidence'" label-placement="top">
          <div class="grid grid-cols-1 gap-x-3 sm:grid-cols-2">
            <n-form-item :label="$t('page.research.evidenceKind')" required>
              <n-select v-model:value="evidenceDraft.kind" :options="evidenceKindOptions" />
            </n-form-item>
            <n-form-item :label="$t('page.research.evidenceSource')" required>
              <n-select v-model:value="evidenceDraft.artifact_type" :options="evidenceSourceOptions" @update:value="resetEvidenceSource" />
            </n-form-item>
          </div>
          <n-form-item v-if="evidenceDraft.artifact_type === 'data_asset'" :label="$t('page.research.dataAsset')" required>
            <n-select v-model:value="evidenceDraft.artifact_id" :options="dataAssetOptions" />
          </n-form-item>
          <template v-else-if="evidenceDraft.artifact_type === 'action_output'">
            <n-alert type="info" class="mb-4">
              {{ $t("page.research.actionOutputEvidenceHint") }}
            </n-alert>
            <n-form-item :label="$t('page.research.actionOutput')" required>
              <n-select v-model:value="evidenceDraft.artifact_id" :options="actionOutputOptions" />
            </n-form-item>
          </template>
          <n-form-item v-else :label="$t('page.research.externalUri')" required>
            <n-input v-model:value="evidenceDraft.artifact_id" placeholder="https://…" />
          </n-form-item>
          <n-form-item :label="$t('page.research.evidenceSummary')">
            <n-input v-model:value="evidenceDraft.summary" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" />
          </n-form-item>
        </n-form>

        <n-form v-else-if="modalKind === 'claim'" label-placement="top">
          <n-alert type="warning" class="mb-4">
            {{ $t("page.research.claimDraftBoundary") }}
          </n-alert>
          <n-form-item :label="$t('page.research.validatedClaimEvidence')">
            <n-select
              v-model:value="selectedEvidenceIds"
              multiple
              clearable
              :options="evidenceOptions"
              @update:value="clearClaimGeneration"
            />
          </n-form-item>
          <div v-if="selectedEvidenceIds.length" class="mb-4 space-y-2">
            <div v-for="evidenceId in selectedEvidenceIds" :key="evidenceId" class="claim-evidence-editor">
              <div class="aira-type-meta mb-2 break-all">
                {{ evidenceLabelById(evidenceId) }}
              </div>
              <div class="grid grid-cols-1 gap-2 sm:grid-cols-[10rem_minmax(0,1fr)]">
                <n-select
                  :value="claimEvidenceValue(evidenceId).relation"
                  :options="claimEvidenceRelationOptions"
                  @update:value="value => updateClaimEvidence(evidenceId, { relation: value })"
                />
                <n-input
                  :value="claimEvidenceValue(evidenceId).rationale"
                  :placeholder="$t('page.research.claimEvidenceRationalePlaceholder')"
                  @update:value="value => updateClaimEvidence(evidenceId, { rationale: value })"
                />
              </div>
            </div>
          </div>
          <div v-if="instanceStore.aiEnabled" class="mb-4 border border-blue-200 rounded-lg bg-blue-50/70 p-3">
            <div class="aira-type-label mb-2">
              {{ $t("page.research.airaClaimDraft") }}
            </div>
            <n-input
              v-model:value="airaClaimInstruction"
              type="textarea"
              :placeholder="$t('page.research.airaClaimInstructionPlaceholder')"
              :autosize="{ minRows: 2, maxRows: 5 }"
            />
            <div class="mt-2 flex flex-wrap items-center justify-between gap-2">
              <span class="aira-type-meta">{{ $t("page.research.airaClaimDraftHint") }}</span>
              <n-button
                size="small"
                type="primary"
                secondary
                :disabled="!canGenerateClaim"
                :loading="airaGenerating"
                @click="generateClaimDraft"
              >
                {{ $t("page.research.generateDraftWithAira") }}
              </n-button>
            </div>
          </div>
          <n-alert v-if="claimDraft.aira_generation" type="success" class="mb-4">
            {{ $t("page.research.airaClaimGenerated", { model: claimDraft.aira_generation.model }) }}
          </n-alert>
          <n-form-item :label="$t('page.research.claimStatement')" required>
            <n-input v-model:value="claimDraft.statement" type="textarea" :autosize="{ minRows: 4, maxRows: 10 }" />
          </n-form-item>
          <n-form-item :label="$t('page.research.confidence')">
            <n-slider v-model:value="claimDraft.confidence" :min="0" :max="1" :step="0.05" :tooltip="true" />
          </n-form-item>
          <n-form-item :label="$t('page.research.uncertainty')">
            <n-input v-model:value="claimDraft.uncertainty" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" />
          </n-form-item>
        </n-form>

        <n-form v-else-if="modalKind === 'knowledge'" label-placement="top">
          <n-alert type="info" class="mb-4">
            {{ $t("page.research.knowledgeSuggestionBoundary") }}
          </n-alert>
          <div class="grid grid-cols-1 gap-x-3 sm:grid-cols-2">
            <n-form-item :label="$t('page.knowledge.knowledgeTitle')" required>
              <n-input v-model:value="knowledgeDraft.title" />
            </n-form-item>
            <n-form-item :label="$t('page.knowledge.kind')" required>
              <n-select v-model:value="knowledgeDraft.kind" :options="knowledgeKindOptions" />
            </n-form-item>
          </div>
          <n-form-item :label="$t('page.knowledge.knowledgeBody')" required>
            <n-input
              v-model:value="knowledgeDraft.body"
              type="textarea"
              :autosize="{ minRows: 5, maxRows: 12 }"
              :placeholder="$t('page.knowledge.knowledgeBodyPlaceholder')"
            />
          </n-form-item>
          <n-form-item :label="$t('page.research.validatedEvidence')" required>
            <n-select
              v-model:value="knowledgeDraft.evidence_ids"
              multiple
              clearable
              :options="knowledgeEvidenceOptions"
            />
          </n-form-item>
          <n-form-item :label="$t('page.knowledge.tags')">
            <n-dynamic-tags v-model:value="knowledgeDraft.tags" />
          </n-form-item>
        </n-form>
        <n-form v-else label-placement="top">
          <n-alert type="warning" class="mb-4">
            {{ $t("page.research.protocolImprovementBoundary") }}
          </n-alert>
          <n-form-item :label="$t('page.research.targetProtocol')" required>
            <n-select
              v-model:value="protocolImprovementDraft.protocol_id"
              :options="protocolOptions"
              @update:value="clearProtocolImprovementGeneration"
            />
          </n-form-item>
          <n-form-item :label="$t('page.research.validatedEvidence')" required>
            <n-select
              v-model:value="protocolImprovementDraft.evidence_ids"
              multiple
              clearable
              :options="knowledgeEvidenceOptions"
              @update:value="clearProtocolImprovementGeneration"
            />
          </n-form-item>
          <div v-if="instanceStore.aiEnabled" class="mb-4 border border-blue-200 rounded-lg bg-blue-50/70 p-3">
            <div class="aira-type-label mb-2">
              {{ $t("page.research.airaImprovementDraft") }}
            </div>
            <n-input
              v-model:value="airaImprovementInstruction"
              type="textarea"
              :placeholder="$t('page.research.airaImprovementInstructionPlaceholder')"
              :autosize="{ minRows: 2, maxRows: 5 }"
            />
            <div class="mt-2 flex flex-wrap items-center justify-between gap-2">
              <span class="aira-type-meta">{{ $t("page.research.airaImprovementDraftHint") }}</span>
              <n-button
                size="small"
                type="primary"
                secondary
                :disabled="!canGenerateProtocolImprovement"
                :loading="airaGenerating"
                @click="generateProtocolImprovementDraft"
              >
                {{ $t("page.research.generateDraftWithAira") }}
              </n-button>
            </div>
          </div>
          <n-alert v-if="protocolImprovementDraft.aira_generation" type="success" class="mb-4">
            {{ $t("page.research.airaImprovementGenerated", { model: protocolImprovementDraft.aira_generation.model }) }}
          </n-alert>
          <n-form-item :label="$t('page.research.improvementTitle')" required>
            <n-input v-model:value="protocolImprovementDraft.title" />
          </n-form-item>
          <n-form-item :label="$t('page.research.improvementRationale')" required>
            <n-input v-model:value="protocolImprovementDraft.rationale" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" />
          </n-form-item>
          <n-form-item :label="$t('page.research.proposedChanges')" required>
            <n-input v-model:value="protocolImprovementDraft.proposed_changes" type="textarea" :autosize="{ minRows: 4, maxRows: 12 }" />
          </n-form-item>
        </n-form>
      </template>
      <template v-else>
        <n-alert type="info">
          {{ $t("page.research.assetPreviewHint") }}
        </n-alert>
        <div class="scientific-preview mt-4">
          <div class="aira-type-eyebrow">
            {{ $t("page.research.saveDestination") }}
          </div>
          <div class="aira-type-card-title mt-1">
            {{ previewDestinationLabel }}
          </div>
          <p class="aira-type-body aira-text-secondary mb-0 mt-3 whitespace-pre-wrap">
            {{ previewSummary }}
          </p>
          <div class="aira-type-meta mt-3 break-all">
            {{ $t("page.research.previewDigest") }} · {{ preview.preview_digest }}
          </div>
        </div>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2">
          <n-button @click="preview ? preview = null : modalVisible = false">
            {{ preview ? $t("page.research.backToEdit") : $t("common.cancel") }}
          </n-button>
          <n-button v-if="!preview" type="primary" :disabled="!canPreview || airaGenerating" :loading="mutating" @click="createPreview">
            {{ $t("page.research.previewAssetWrite") }}
          </n-button>
          <n-button v-else type="primary" :loading="mutating" @click="confirmCreate">
            {{ $t("page.research.confirmAssetWrite") }}
          </n-button>
        </div>
      </template>
    </n-modal>
  </section>
</template>

<script setup lang="ts">
import type {
  AssetPreview,
  ClaimDraft,
  ClaimEvidenceRelation,
  ClaimState,
  DataAsset,
  DataAssetDraft,
  DataAssetKind,
  EvidenceArtifactType,
  EvidenceDraft,
  EvidenceKind,
  EvidenceQuality,
  KnowledgeSuggestionDraft,
  ProtocolImprovementDraft,
  ProtocolImprovementProposal,
  ProtocolImprovementState,
  ResearchAssetBundle,
  ResearchClaim,
  ResearchEvidence,
  ResearchKnowledgeItem,
  ResearchKnowledgeKind,
} from "@/service/api/research-assets"
import type { ResearchAction, ResearchProtocolRef } from "@/service/api/research-tasks"
import type { TagProps } from "naive-ui"
import {
  createClaim,
  createDataAsset,
  createEvidence,
  createKnowledgeSuggestion,
  createProtocolImprovement,
  draftClaimWithAira,
  draftProtocolImprovementWithAira,
  fetchResearchAssets,
  previewClaim,
  previewDataAsset,
  previewEvidence,
  previewKnowledgeSuggestion,
  previewProtocolImprovement,
  reviewClaim,
  reviewEvidence,
  reviewProtocolImprovement,
  updateDataAssetStatus,
} from "@/service/api/research-assets"
import { useInstanceStore } from "@/store/modules/instance"
import { $t } from "@airalogy/shared/locales"
import { useDialog } from "naive-ui"
import { useRouter } from "vue-router"

const props = defineProps<{
  taskId: string
  labUid: string
  projectUid: string
  protocols: ResearchProtocolRef[]
  actions: ResearchAction[]
}>()

const emit = defineEmits<{
  changed: []
}>()

type ModalKind = "asset" | "evidence" | "claim" | "knowledge" | "protocolImprovement"

const emptyBundle = (): ResearchAssetBundle => ({ data_assets: [], evidence: [], claims: [], knowledge_items: [], protocol_improvements: [] })
const dialog = useDialog()
const router = useRouter()
const instanceStore = useInstanceStore()
const bundle = ref<ResearchAssetBundle>(emptyBundle())
const loading = ref(false)
const loadError = ref(false)
const mutating = ref(false)
const modalVisible = ref(false)
const modalKind = ref<ModalKind>("asset")
const preview = ref<AssetPreview<any> | null>(null)
const selectedEvidenceIds = ref<string[]>([])

const assetDraft = reactive<DataAssetDraft>(newAssetDraft())
const evidenceDraft = reactive<EvidenceDraft>(newEvidenceDraft())
const claimDraft = reactive<ClaimDraft>(newClaimDraft())
const knowledgeDraft = reactive<KnowledgeSuggestionDraft>(newKnowledgeDraft())
const protocolImprovementDraft = reactive<ProtocolImprovementDraft>(newProtocolImprovementDraft())
const airaClaimInstruction = ref("")
const airaImprovementInstruction = ref("")
const airaGenerating = ref(false)

const isEmpty = computed(() => !bundle.value.data_assets.length && !bundle.value.evidence.length && !bundle.value.claims.length && !bundle.value.knowledge_items.length && !bundle.value.protocol_improvements.length)
const modalTitle = computed(() => {
  const keys: Record<ModalKind, I18n.I18nKey> = {
    asset: "page.research.addDataAsset",
    evidence: "page.research.addEvidence",
    claim: "page.research.addClaim",
    knowledge: "page.research.suggestKnowledge",
    protocolImprovement: "page.research.proposeProtocolImprovement",
  }
  return $t(keys[modalKind.value])
})
const assetKindValues: DataAssetKind[] = ["file", "table", "image", "model", "archive", "external"]
const assetKindOptions = computed(() => assetKindValues.map(value => ({ value, label: dataAssetKindLabel(value) })))
const evidenceKindValues: EvidenceKind[] = ["observation", "measurement", "analysis", "citation", "validation"]
const evidenceKindOptions = computed(() => evidenceKindValues.map(value => ({ value, label: evidenceKindLabel(value) })))
const actionOutputOptions = computed(() => props.actions
  .filter(action => action.status === "completed" && Object.keys(action.output_data || {}).length)
  .filter(action => action.requirements?.risk !== "model_advisory"
    && action.input_data?.tool_key !== "aira.specialist"
    && action.output_data?.tool_key !== "aira.specialist")
  .map(action => ({
    value: action.id,
    label: `${action.title} · ${action.kind}`,
  })))
const evidenceSourceOptions = computed(() => ([
  { value: "data_asset", label: $t("page.research.dataAsset") },
  {
    value: "action_output",
    label: $t("page.research.actionOutput"),
    disabled: !actionOutputOptions.value.length,
  },
  { value: "external", label: $t("page.research.externalSource") },
]))
const dataAssetOptions = computed(() => bundle.value.data_assets.map(asset => ({
  value: asset.id,
  label: `${asset.name} · v${asset.current_version}`,
})))
const evidenceOptions = computed(() => bundle.value.evidence.map(item => ({
  value: item.id,
  label: `${item.summary || artifactLabel(item)} · ${evidenceStateLabel(item.quality_state)}`,
})))
const claimEvidenceRelationValues: ClaimEvidenceRelation[] = ["supports", "contradicts", "context"]
const claimEvidenceRelationOptions = computed(() => claimEvidenceRelationValues.map(value => ({
  value,
  label: claimRelationLabel(value),
})))
const validatedEvidenceIds = computed(() => new Set(
  bundle.value.evidence
    .filter(item => item.quality_state === "validated")
    .map(item => item.id),
))
const knowledgeKindValues: ResearchKnowledgeKind[] = ["note", "method", "decision", "finding"]
const knowledgeKindOptions = computed(() => knowledgeKindValues.map(value => ({ value, label: knowledgeKindLabel(value) })))
const knowledgeEvidenceOptions = computed(() => bundle.value.evidence
  .filter(item => item.quality_state === "validated" && ["record", "data_asset", "action_output"].includes(item.artifact_type))
  .map(item => ({
    value: item.id,
    label: item.summary || artifactLabel(item),
  })))
const protocolOptions = computed(() => props.protocols.map(protocol => ({
  value: protocol.id,
  label: `${protocol.name} · v${protocol.version}`,
})))
const canGenerateProtocolImprovement = computed(() => Boolean(
  protocolImprovementDraft.protocol_id
  && protocolImprovementDraft.evidence_ids.length,
))
const canGenerateClaim = computed(() => Boolean(
  selectedEvidenceIds.value.length
  && selectedEvidenceIds.value.every(id => validatedEvidenceIds.value.has(id)),
))
const canPreview = computed(() => {
  if (modalKind.value === "asset")
    return Boolean(assetDraft.name.trim() && assetDraft.external_uri.trim())
  if (modalKind.value === "evidence")
    return Boolean(evidenceDraft.artifact_id.trim())
  if (modalKind.value === "claim")
    return Boolean(claimDraft.statement.trim())
  if (modalKind.value === "knowledge")
    return Boolean(knowledgeDraft.title.trim() && knowledgeDraft.body.trim() && knowledgeDraft.evidence_ids.length)
  return Boolean(
    protocolImprovementDraft.protocol_id
    && protocolImprovementDraft.title.trim()
    && protocolImprovementDraft.rationale.trim()
    && protocolImprovementDraft.proposed_changes.trim()
    && protocolImprovementDraft.evidence_ids.length,
  )
})
const previewSummary = computed(() => {
  if (modalKind.value === "asset")
    return `${assetDraft.name}\n${assetDraft.external_uri}`
  if (modalKind.value === "evidence")
    return evidenceDraft.summary || evidenceDraft.artifact_id
  if (modalKind.value === "claim")
    return claimDraft.statement
  if (modalKind.value === "knowledge")
    return `${knowledgeDraft.title}\n${knowledgeDraft.body}`
  return `${protocolImprovementDraft.title}\n${protocolImprovementDraft.proposed_changes}`
})
const previewDestinationLabel = computed(() => preview.value?.destination.project_name || preview.value?.destination.task_title || "")

function newAssetDraft(): DataAssetDraft {
  return {
    task_id: props.taskId,
    name: "",
    description: "",
    kind: "file",
    external_uri: "",
    media_type: "",
    checksum: "",
    data_schema: {},
    metadata: {},
    source: { registered_from: "research_task_workbench" },
    change_summary: "Created from Research Task workbench",
  }
}

function newEvidenceDraft(): EvidenceDraft {
  return {
    task_id: props.taskId,
    kind: "observation",
    artifact_type: "data_asset",
    artifact_id: "",
    artifact_version: "",
    summary: "",
  }
}

function newClaimDraft(): ClaimDraft {
  return {
    task_id: props.taskId,
    statement: "",
    confidence: 0.5,
    uncertainty: "",
    evidence: [],
  }
}

function newKnowledgeDraft(): KnowledgeSuggestionDraft {
  return {
    task_id: props.taskId,
    title: "",
    body: "",
    kind: "finding",
    tags: [],
    evidence_ids: [],
  }
}

function newProtocolImprovementDraft(): ProtocolImprovementDraft {
  return {
    task_id: props.taskId,
    protocol_id: props.protocols.length === 1 ? props.protocols[0].id : "",
    title: "",
    rationale: "",
    proposed_changes: "",
    evidence_ids: [],
  }
}

async function loadAssets() {
  loading.value = true
  loadError.value = false
  try {
    bundle.value = await fetchResearchAssets(props.taskId)
  }
  catch {
    loadError.value = true
  }
  finally {
    loading.value = false
  }
}

function openModal(kind: ModalKind) {
  modalKind.value = kind
  modalVisible.value = true
}

function openProjectKnowledge() {
  return router.push({
    name: "project-knowledge",
    params: { labUid: props.labUid, projectUid: props.projectUid },
  })
}

function resetModal() {
  preview.value = null
  selectedEvidenceIds.value = []
  Object.assign(assetDraft, newAssetDraft())
  Object.assign(evidenceDraft, newEvidenceDraft())
  Object.assign(claimDraft, newClaimDraft())
  Object.assign(knowledgeDraft, newKnowledgeDraft())
  Object.assign(protocolImprovementDraft, newProtocolImprovementDraft())
  airaClaimInstruction.value = ""
  airaImprovementInstruction.value = ""
}

function clearClaimGeneration() {
  const hadGeneration = Boolean(claimDraft.aira_generation)
  delete claimDraft.aira_generation
  delete claimDraft.aira_receipt
  if (hadGeneration) {
    claimDraft.statement = ""
    claimDraft.confidence = 0.5
    claimDraft.uncertainty = ""
    claimDraft.evidence = []
    window.$message?.info($t("page.research.airaClaimContextChanged"))
  }
}

function claimEvidenceValue(evidenceId: string): ClaimDraft["evidence"][number] {
  return claimDraft.evidence.find(item => item.evidence_id === evidenceId) || {
    evidence_id: evidenceId,
    relation: "supports",
    rationale: "",
  }
}

function updateClaimEvidence(
  evidenceId: string,
  update: Partial<Pick<ClaimDraft["evidence"][number], "relation" | "rationale">>,
) {
  const current = claimEvidenceValue(evidenceId)
  const next = { ...current, ...update }
  const index = claimDraft.evidence.findIndex(item => item.evidence_id === evidenceId)
  if (index === -1)
    claimDraft.evidence.push(next)
  else
    claimDraft.evidence.splice(index, 1, next)
}

async function generateClaimDraft() {
  if (!canGenerateClaim.value)
    return
  airaGenerating.value = true
  try {
    const draft = await draftClaimWithAira({
      task_id: props.taskId,
      evidence_ids: [...selectedEvidenceIds.value],
      instruction: airaClaimInstruction.value.trim(),
    })
    Object.assign(claimDraft, draft)
    selectedEvidenceIds.value = draft.evidence.map(item => item.evidence_id)
    window.$message?.success($t("page.research.airaClaimDraftReady"))
  }
  finally {
    airaGenerating.value = false
  }
}

function clearProtocolImprovementGeneration() {
  const hadGeneration = Boolean(protocolImprovementDraft.aira_generation)
  delete protocolImprovementDraft.aira_generation
  delete protocolImprovementDraft.aira_receipt
  if (hadGeneration) {
    protocolImprovementDraft.title = ""
    protocolImprovementDraft.rationale = ""
    protocolImprovementDraft.proposed_changes = ""
    window.$message?.info($t("page.research.airaImprovementContextChanged"))
  }
}

async function generateProtocolImprovementDraft() {
  if (!canGenerateProtocolImprovement.value)
    return
  airaGenerating.value = true
  try {
    const draft = await draftProtocolImprovementWithAira({
      task_id: props.taskId,
      protocol_id: protocolImprovementDraft.protocol_id,
      evidence_ids: [...protocolImprovementDraft.evidence_ids],
      instruction: airaImprovementInstruction.value.trim(),
    })
    Object.assign(protocolImprovementDraft, draft)
    window.$message?.success($t("page.research.airaImprovementDraftReady"))
  }
  finally {
    airaGenerating.value = false
  }
}

function resetEvidenceSource(value: EvidenceArtifactType) {
  evidenceDraft.artifact_type = value
  evidenceDraft.artifact_id = ""
  evidenceDraft.artifact_version = ""
  delete evidenceDraft.run_id
  delete evidenceDraft.action_id
}

function normalizedEvidenceDraft(): EvidenceDraft {
  const asset = evidenceDraft.artifact_type === "data_asset"
    ? bundle.value.data_assets.find(item => item.id === evidenceDraft.artifact_id)
    : undefined
  const action = evidenceDraft.artifact_type === "action_output"
    ? props.actions.find(item => item.id === evidenceDraft.artifact_id)
    : undefined
  return {
    ...evidenceDraft,
    run_id: action?.run_id,
    action_id: action?.id,
    artifact_version: asset ? String(asset.current_version) : "",
  }
}

function normalizedClaimDraft(): ClaimDraft {
  return {
    ...claimDraft,
    evidence: selectedEvidenceIds.value.map((evidenceId) => {
      const generated = claimDraft.evidence.find(item => item.evidence_id === evidenceId)
      return generated || {
        evidence_id: evidenceId,
        relation: "supports",
        rationale: "",
      }
    }),
  }
}

async function createPreview() {
  mutating.value = true
  try {
    if (modalKind.value === "asset")
      preview.value = await previewDataAsset({ ...assetDraft })
    else if (modalKind.value === "evidence")
      preview.value = await previewEvidence(normalizedEvidenceDraft())
    else if (modalKind.value === "claim")
      preview.value = await previewClaim(normalizedClaimDraft())
    else if (modalKind.value === "knowledge")
      preview.value = await previewKnowledgeSuggestion({ ...knowledgeDraft })
    else
      preview.value = await previewProtocolImprovement({ ...protocolImprovementDraft })
  }
  finally {
    mutating.value = false
  }
}

async function confirmCreate() {
  if (!preview.value)
    return
  mutating.value = true
  try {
    if (modalKind.value === "asset") {
      await createDataAsset({ ...assetDraft, preview_digest: preview.value.preview_digest })
    }
    else if (modalKind.value === "evidence") {
      await createEvidence({ ...normalizedEvidenceDraft(), preview_digest: preview.value.preview_digest })
    }
    else if (modalKind.value === "claim") {
      await createClaim({ ...normalizedClaimDraft(), preview_digest: preview.value.preview_digest })
    }
    else if (modalKind.value === "knowledge") {
      await createKnowledgeSuggestion({ ...knowledgeDraft, preview_digest: preview.value.preview_digest })
    }
    else {
      await createProtocolImprovement({ ...protocolImprovementDraft, preview_digest: preview.value.preview_digest })
    }
    modalVisible.value = false
    window.$message?.success($t("page.research.assetWriteCompleted"))
    await loadAssets()
    emit("changed")
  }
  finally {
    mutating.value = false
  }
}

function confirmAssetReady(asset: DataAsset) {
  dialog.success({
    title: $t("page.research.markReady"),
    content: $t("page.research.markReadyConfirm"),
    positiveText: $t("common.confirm"),
    negativeText: $t("common.cancel"),
    onPositiveClick: async () => {
      await updateDataAssetStatus(asset, "ready")
      await loadAssets()
      emit("changed")
    },
  })
}

function confirmEvidenceReview(item: ResearchEvidence, state: "validated" | "rejected") {
  dialog.warning({
    title: state === "validated" ? $t("page.research.validateEvidence") : $t("page.research.rejectEvidence"),
    content: $t("page.research.evidenceReviewConfirm"),
    positiveText: $t("common.confirm"),
    negativeText: $t("common.cancel"),
    onPositiveClick: async () => {
      await reviewEvidence(item, state)
      await loadAssets()
      emit("changed")
    },
  })
}

function confirmClaimReview(item: ResearchClaim, state: "reviewed" | "rejected") {
  dialog.warning({
    title: state === "reviewed" ? $t("page.research.acceptClaim") : $t("page.research.rejectClaim"),
    content: $t("page.research.claimReviewConfirm"),
    positiveText: $t("common.confirm"),
    negativeText: $t("common.cancel"),
    onPositiveClick: async () => {
      await reviewClaim(item, state)
      await loadAssets()
      emit("changed")
    },
  })
}

function confirmProtocolImprovementReview(item: ProtocolImprovementProposal, state: "reviewed" | "rejected") {
  dialog.warning({
    title: state === "reviewed" ? $t("page.research.acceptProtocolImprovement") : $t("page.research.rejectProtocolImprovement"),
    content: $t("page.research.protocolImprovementReviewConfirm"),
    positiveText: $t("common.confirm"),
    negativeText: $t("common.cancel"),
    onPositiveClick: async () => {
      await reviewProtocolImprovement(item, state)
      await loadAssets()
      emit("changed")
    },
  })
}

function openProtocolImprovementDraft(proposal: ProtocolImprovementProposal) {
  const protocol = props.protocols.find(item => item.id === proposal.protocol_id)
  if (!protocol)
    return
  return router.push({
    name: "protocol-editor",
    params: {
      labUid: protocol.lab_uid || props.labUid,
      projectUid: protocol.project_uid || props.projectUid,
      protocolUid: protocol.uid,
      protocolVersion: proposal.base_protocol_version,
    },
    query: {
      protocol_improvement_id: proposal.id,
      protocol_improvement_revision: String(proposal.revision),
    },
  })
}

function openAppliedProtocol(proposal: ProtocolImprovementProposal) {
  const protocol = props.protocols.find(item => item.id === proposal.protocol_id)
  if (!protocol)
    return
  return router.push({
    name: "protocol-editor",
    params: {
      labUid: protocol.lab_uid || props.labUid,
      projectUid: protocol.project_uid || props.projectUid,
      protocolUid: protocol.uid,
      protocolVersion: proposal.applied_protocol_version || protocol.version,
    },
  })
}

function currentVersion(asset: DataAsset) {
  return asset.versions.find(version => version.version === asset.current_version)
}

function artifactLabel(item: ResearchEvidence) {
  if (item.artifact_type === "action_output")
    return `${artifactTypeLabel(item.artifact_type)} · ${item.artifact_id} · sha256:${item.artifact_version.slice(0, 12)}`
  return `${artifactTypeLabel(item.artifact_type)} · ${item.artifact_id}${item.artifact_version ? ` · v${item.artifact_version}` : ""}`
}

function formatActionOutput(value: Record<string, unknown>) {
  return JSON.stringify(value, null, 2)
}

function evidenceLabelById(evidenceId: string) {
  const evidence = bundle.value.evidence.find(item => item.id === evidenceId)
  return evidence ? evidence.summary || artifactLabel(evidence) : evidenceId
}

function claimRelationLabel(value: ClaimEvidenceRelation) {
  return $t(`page.research.claimEvidenceRelation.${value}` as I18n.I18nKey)
}

function claimRelationType(value: ClaimEvidenceRelation): TagProps["type"] {
  if (value === "supports")
    return "success"
  if (value === "contradicts")
    return "error"
  return "default"
}

function claimStateType(state: ClaimState): TagProps["type"] {
  if (state === "reviewed")
    return "success"
  if (state === "rejected")
    return "error"
  return "warning"
}

function evidenceStateType(state: EvidenceQuality): TagProps["type"] {
  if (state === "validated")
    return "success"
  if (state === "rejected")
    return "error"
  return "warning"
}

function protocolImprovementStateType(state: ProtocolImprovementState): TagProps["type"] {
  if (state === "applied")
    return "success"
  if (state === "reviewed")
    return "info"
  if (state === "rejected")
    return "error"
  return "warning"
}

function protocolImprovementStateLabel(value: ProtocolImprovementState) {
  return $t(`page.research.protocolImprovementState.${value}` as I18n.I18nKey)
}

function claimStateLabel(value: ClaimState) {
  return $t(`page.research.claimState.${value}` as I18n.I18nKey)
}

function evidenceStateLabel(value: EvidenceQuality) {
  return $t(`page.research.evidenceQuality.${value}` as I18n.I18nKey)
}

function evidenceKindLabel(value: EvidenceKind) {
  return $t(`page.research.evidenceKindValue.${value}` as I18n.I18nKey)
}

function artifactTypeLabel(value: EvidenceArtifactType) {
  return $t(`page.research.artifactType.${value}` as I18n.I18nKey)
}

function dataAssetKindLabel(value: DataAssetKind) {
  return $t(`page.research.dataAssetKind.${value}` as I18n.I18nKey)
}

function dataAssetStatusLabel(value: DataAsset["status"]) {
  return $t(`page.research.dataAssetStatus.${value}` as I18n.I18nKey)
}

function knowledgeKindLabel(value: ResearchKnowledgeKind) {
  const keys: Record<ResearchKnowledgeKind, I18n.I18nKey> = {
    note: "page.knowledge.kindNote",
    method: "page.knowledge.kindMethod",
    decision: "page.knowledge.kindDecision",
    finding: "page.knowledge.kindFinding",
  }
  return $t(keys[value])
}

function knowledgeStateLabel(value: ResearchKnowledgeItem["state"]) {
  const keys: Record<ResearchKnowledgeItem["state"], I18n.I18nKey> = {
    suggested: "page.knowledge.stateSuggested",
    draft: "page.knowledge.stateDraft",
    reviewed: "page.knowledge.stateReviewed",
    superseded: "page.knowledge.stateSuperseded",
    archived: "page.knowledge.stateArchived",
  }
  return $t(keys[value])
}

onMounted(loadAssets)
watch(() => props.taskId, () => {
  resetModal()
  loadAssets()
})
</script>

<style scoped>
.research-assets-panel {
  border: 1px solid rgb(229 231 235);
  border-radius: 0.875rem;
  background: white;
  padding: 1.25rem;
}

.scientific-card,
.scientific-preview {
  border: 1px solid rgb(226 232 240);
  border-radius: 0.75rem;
  background: rgb(248 250 252 / 72%);
  padding: 1rem;
}

.scientific-change {
  border-left: 3px solid rgb(245 158 11 / 60%);
  background: rgb(255 251 235 / 75%);
  padding: 0.75rem 0.875rem;
}

.claim-evidence-row,
.claim-evidence-editor {
  border: 1px solid rgb(226 232 240 / 85%);
  border-radius: 0.75rem;
  background: rgb(248 250 252 / 75%);
  padding: 0.75rem;
}

.action-output-json {
  max-height: 20rem;
  overflow: auto;
  border-radius: 0.75rem;
  background: rgb(15 23 42);
  color: rgb(226 232 240);
  font-size: 0.75rem;
  line-height: 1.5;
  padding: 0.875rem;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>

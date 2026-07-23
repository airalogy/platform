<template>
  <div class="resource-library">
    <section class="resource-library__hero">
      <div>
        <p class="resource-library__eyebrow">
          {{ $t("page.resourceLibrary.labWorkspace") }}
        </p>
        <h2>{{ $t("page.resourceLibrary.title") }}</h2>
        <p>{{ $t("page.resourceLibrary.description") }}</p>
      </div>
      <n-space>
        <n-button secondary @click="openScanModal">
          <template #icon>
            <icon-tabler-scan />
          </template>
          {{ $t("page.resourceLibrary.scan") }}
        </n-button>
        <n-button v-if="activeSection === 'resources'" type="primary" @click="resourceModalVisible = true">
          <template #icon>
            <icon-ion-add-outline />
          </template>
          {{ $t("page.resourceLibrary.addResource") }}
        </n-button>
      </n-space>
    </section>

    <n-tabs
      :value="activeSection"
      type="line"
      animated
      class="resource-library__tabs"
      @update:value="navigateSection"
    >
      <n-tab v-for="section in sections" :key="section.value" :name="section.value">
        {{ section.label }}
        <n-badge
          v-if="section.value === 'reminders' && overview.unread_notifications"
          :value="overview.unread_notifications"
          :max="99"
          class="ml-1"
        />
      </n-tab>
    </n-tabs>

    <n-spin :show="loading">
      <template v-if="activeSection === 'overview'">
        <n-grid cols="1 s:2 l:5" responsive="screen" :x-gap="16" :y-gap="16">
          <n-grid-item v-for="card in overviewCards" :key="card.key">
            <article class="metric-card">
              <span>{{ card.label }}</span>
              <strong>{{ card.value }}</strong>
              <small>{{ card.hint }}</small>
            </article>
          </n-grid-item>
        </n-grid>
        <section class="resource-library__panel mt-5">
          <div class="panel-heading">
            <div>
              <h3>{{ $t("page.resourceLibrary.recentResources") }}</h3>
              <p>{{ $t("page.resourceLibrary.recentResourcesHint") }}</p>
            </div>
            <n-button text type="primary" @click="navigateSection('resources')">
              {{ $t("common.viewAll") }}
            </n-button>
          </div>
          <n-data-table
            :columns="resourceColumns"
            :data="resources.slice(0, 6)"
            :bordered="false"
            :single-line="false"
            :row-props="resourceRowProps"
          />
        </section>
      </template>

      <template v-else-if="activeSection === 'resources'">
        <section class="resource-library__panel">
          <div class="toolbar">
            <n-input
              v-model:value="filters.q"
              clearable
              class="max-w-80"
              :placeholder="$t('page.resourceLibrary.searchPlaceholder')"
              @keyup.enter="loadResources"
            >
              <template #prefix>
                <icon-tabler-search />
              </template>
            </n-input>
            <n-select
              v-model:value="filters.resourceTypeId"
              clearable
              class="w-56"
              :options="resourceTypeOptions"
              :placeholder="$t('page.resourceLibrary.resourceType')"
              @update:value="loadResources"
            />
            <n-select
              v-model:value="filters.status"
              clearable
              class="w-44"
              :options="statusOptions"
              :placeholder="$t('common.status')"
              @update:value="loadResources"
            />
            <n-button @click="loadResources">
              {{ $t("common.search") }}
            </n-button>
            <div class="ml-auto flex gap-2">
              <n-button secondary @click="importModalVisible = true">
                {{ $t("common.import") }}
              </n-button>
              <n-button type="primary" @click="resourceModalVisible = true">
                {{ $t("page.resourceLibrary.addResource") }}
              </n-button>
            </div>
          </div>
          <n-data-table
            :columns="resourceColumns"
            :data="resources"
            :bordered="false"
            :single-line="false"
            :row-props="resourceRowProps"
            :scroll-x="980"
          />
          <n-empty v-if="!resources.length && !loading" :description="$t('page.resourceLibrary.noResources')" class="py-16" />
        </section>
      </template>

      <template v-else-if="activeSection === 'inventory' || activeSection === 'events'">
        <section class="resource-library__panel">
          <div class="panel-heading">
            <div>
              <h3>{{ activeSection === "inventory" ? $t("page.resourceLibrary.inventory") : $t("page.resourceLibrary.events") }}</h3>
              <p>{{ $t("page.resourceLibrary.appendOnlyHint") }}</p>
            </div>
            <n-button secondary @click="exportInventory">
              {{ $t("common.export") }}
            </n-button>
            <template v-if="activeSection === 'inventory'">
              <n-button secondary @click="transferModalVisible = true">
                {{ $t("page.resourceLibrary.transferInventory") }}
              </n-button>
              <n-button secondary @click="reservationModalVisible = true">
                {{ $t("page.resourceLibrary.reserveInventory") }}
              </n-button>
              <n-button type="primary" @click="inventoryModalVisible = true">
                {{ $t("page.resourceLibrary.recordInventory") }}
              </n-button>
            </template>
          </div>
          <n-data-table
            :columns="inventoryColumns"
            :data="inventoryEvents"
            :bordered="false"
            :single-line="false"
            :scroll-x="1100"
          />
          <template v-if="activeSection === 'inventory'">
            <h3 class="mb-3 mt-8">
              {{ $t("page.resourceLibrary.reservations") }}
            </h3>
            <n-data-table
              :columns="reservationColumns"
              :data="reservations"
              :bordered="false"
              :single-line="false"
              :scroll-x="900"
            />
          </template>
        </section>
      </template>

      <template v-else-if="activeSection === 'locations'">
        <section class="resource-library__panel">
          <div class="panel-heading">
            <div>
              <h3>{{ $t("page.resourceLibrary.locations") }}</h3>
              <p>{{ $t("page.resourceLibrary.locationsHint") }}</p>
            </div>
            <n-button type="primary" @click="locationModalVisible = true">
              {{ $t("page.resourceLibrary.addLocation") }}
            </n-button>
          </div>
          <n-data-table :columns="locationColumns" :data="locations" :bordered="false" :single-line="false" />
        </section>
      </template>

      <template v-else-if="activeSection === 'bookings'">
        <section class="resource-library__panel">
          <div class="panel-heading">
            <div>
              <h3>{{ $t("page.resourceLibrary.bookings") }}</h3>
              <p>{{ $t("page.resourceLibrary.bookingsHint") }}</p>
            </div>
            <n-button type="primary" @click="bookingModalVisible = true">
              {{ $t("page.resourceLibrary.newBooking") }}
            </n-button>
          </div>
          <n-data-table :columns="bookingColumns" :data="bookings" :bordered="false" :single-line="false" :scroll-x="980" />
        </section>
      </template>

      <template v-else-if="activeSection === 'reminders'">
        <section class="resource-library__panel">
          <div class="panel-heading">
            <div>
              <h3>{{ $t("page.resourceLibrary.reminders") }}</h3>
              <p>{{ $t("page.resourceLibrary.remindersHint") }}</p>
            </div>
          </div>
          <div class="notification-list">
            <button
              v-for="item in notifications"
              :key="item.id"
              type="button"
              class="notification-item"
              :class="{ 'notification-item--unread': !item.read_at }"
              @click="markNotificationRead(item)"
            >
              <span class="notification-item__dot" />
              <span>
                <strong>{{ item.title }}</strong>
                <small>{{ item.message }}</small>
              </span>
              <time>{{ formatDate(item.due_at || item.created_at) }}</time>
            </button>
          </div>
          <n-empty v-if="!notifications.length" :description="$t('page.resourceLibrary.noReminders')" class="py-16" />
        </section>
      </template>

      <template v-else-if="activeSection === 'types'">
        <section class="resource-library__panel">
          <div class="panel-heading">
            <div>
              <h3>{{ $t("page.resourceLibrary.types") }}</h3>
              <p>{{ $t("page.resourceLibrary.typesHint") }}</p>
            </div>
            <n-button type="primary" @click="openNewResourceType">
              {{ $t("page.resourceLibrary.registerType") }}
            </n-button>
          </div>
          <n-data-table :columns="typeColumns" :data="resourceTypes" :bordered="false" :single-line="false" :scroll-x="900" />
          <h3 class="mt-8">
            {{ $t("page.resourceLibrary.builtinTemplates") }}
          </h3>
          <div class="template-grid mt-3">
            <article v-for="template in templates" :key="template.id" class="template-card">
              <div>
                <strong>{{ template.name }}</strong>
                <small>{{ template.name_en }}</small>
              </div>
              <n-space>
                <n-tag v-for="(_, capability) in enabledCapabilities(template.capabilities)" :key="capability" size="small">
                  {{ capability }}
                </n-tag>
              </n-space>
              <n-button text type="primary" @click="showTemplate(template)">
                {{ $t("page.resourceLibrary.viewTemplate") }}
              </n-button>
              <n-button text type="primary" @click="downloadTemplate(template)">
                {{ $t("page.resourceLibrary.downloadTemplate") }}
              </n-button>
            </article>
          </div>
        </section>
      </template>
    </n-spin>
  </div>

  <n-modal v-model:show="resourceModalVisible" preset="dialog" :title="$t('page.resourceLibrary.addResource')" :show-icon="false" class="resource-dialog">
    <n-form label-placement="top">
      <n-form-item :label="$t('page.resourceLibrary.resourceType')" required>
        <n-select v-model:value="resourceDraft.resource_type_id" :options="resourceTypeOptions" />
      </n-form-item>
      <div class="form-grid">
        <n-form-item :label="$t('common.name')" required>
          <n-input v-model:value="resourceDraft.name" />
        </n-form-item>
        <n-form-item :label="$t('page.resourceLibrary.stableCode')" required>
          <n-input v-model:value="resourceDraft.code" />
        </n-form-item>
      </div>
      <n-form-item :label="$t('page.resourceLibrary.visibility')">
        <n-radio-group v-model:value="resourceDraft.visibility">
          <n-radio-button value="lab">
            {{ $t("page.resourceLibrary.labVisible") }}
          </n-radio-button>
          <n-radio-button value="restricted">
            {{ $t("page.resourceLibrary.restricted") }}
          </n-radio-button>
        </n-radio-group>
      </n-form-item>
      <n-form-item :label="$t('page.resourceLibrary.schemaData')" :feedback="resourceJsonError" :validation-status="resourceJsonError ? 'error' : undefined">
        <n-input v-model:value="resourceDraft.data" type="textarea" :rows="8" placeholder="{ }" />
      </n-form-item>
    </n-form>
    <template #action>
      <n-button @click="resourceModalVisible = false">
        {{ $t("common.cancel") }}
      </n-button>
      <n-button type="primary" :loading="saving" @click="saveResource">
        {{ $t("common.confirm") }}
      </n-button>
    </template>
  </n-modal>

  <n-modal v-model:show="locationModalVisible" preset="dialog" :title="$t('page.resourceLibrary.addLocation')" :show-icon="false">
    <n-form label-placement="top">
      <n-form-item :label="$t('common.name')" required>
        <n-input v-model:value="locationDraft.name" />
      </n-form-item>
      <n-form-item :label="$t('page.resourceLibrary.stableCode')" required>
        <n-input v-model:value="locationDraft.code" />
      </n-form-item>
      <n-form-item :label="$t('page.resourceLibrary.parentLocation')">
        <n-select v-model:value="locationDraft.parent_id" clearable :options="locationOptions" />
      </n-form-item>
    </n-form>
    <template #action>
      <n-button @click="locationModalVisible = false">
        {{ $t("common.cancel") }}
      </n-button>
      <n-button type="primary" :loading="saving" @click="saveLocation">
        {{ $t("common.confirm") }}
      </n-button>
    </template>
  </n-modal>

  <n-modal v-model:show="bookingModalVisible" preset="dialog" :title="$t('page.resourceLibrary.newBooking')" :show-icon="false">
    <n-form label-placement="top">
      <n-form-item :label="$t('page.resourceLibrary.equipment')" required>
        <n-select v-model:value="bookingDraft.resource_id" filterable :options="equipmentOptions" />
      </n-form-item>
      <n-form-item :label="$t('page.resourceLibrary.bookingRange')" required>
        <n-date-picker v-model:value="bookingDraft.range" type="datetimerange" class="w-full" />
      </n-form-item>
      <n-form-item :label="$t('page.resourceLibrary.purpose')">
        <n-input v-model:value="bookingDraft.purpose" type="textarea" />
      </n-form-item>
    </n-form>
    <template #action>
      <n-button @click="bookingModalVisible = false">
        {{ $t("common.cancel") }}
      </n-button>
      <n-button type="primary" :loading="saving" @click="saveBooking">
        {{ $t("common.confirm") }}
      </n-button>
    </template>
  </n-modal>

  <n-modal
    v-model:show="typeModalVisible"
    preset="dialog"
    :title="editingResourceType ? $t('page.resourceLibrary.upgradeType') : $t('page.resourceLibrary.registerType')"
    :show-icon="false"
    class="resource-dialog"
  >
    <n-alert type="info" class="mb-4">
      {{ $t("page.resourceLibrary.registerTypeHint") }}
    </n-alert>
    <n-form label-placement="top">
      <n-form-item :label="$t('page.resourceLibrary.protocolVersionId')" required>
        <n-select
          v-model:value="typeDraft.protocol_version_id"
          filterable
          :options="resourceDefinitionOptions"
          :placeholder="$t('page.resourceLibrary.selectResourceDefinition')"
        />
      </n-form-item>
      <div class="form-grid">
        <n-form-item :label="$t('common.name')" required>
          <n-input v-model:value="typeDraft.name" />
        </n-form-item>
        <n-form-item :label="$t('page.resourceLibrary.stableCode')" required>
          <n-input v-model:value="typeDraft.code" :disabled="!!editingResourceType" />
        </n-form-item>
      </div>
      <n-form-item :label="$t('page.resourceLibrary.capabilities')">
        <n-checkbox-group v-model:value="typeDraft.capabilities">
          <n-space>
            <n-checkbox v-for="item in capabilityOptions" :key="item" :value="item">
              {{ item }}
            </n-checkbox>
          </n-space>
        </n-checkbox-group>
      </n-form-item>
      <n-form-item :label="$t('page.resourceLibrary.bookingPolicy')">
        <n-select v-model:value="typeDraft.booking_policy" :options="bookingPolicyOptions" />
      </n-form-item>
    </n-form>
    <template #action>
      <n-button @click="typeModalVisible = false">
        {{ $t("common.cancel") }}
      </n-button>
      <n-button type="primary" :loading="saving" @click="saveResourceType">
        {{ $t("common.confirm") }}
      </n-button>
    </template>
  </n-modal>

  <n-modal
    v-model:show="migrationModalVisible"
    preset="card"
    class="resource-migration-modal"
    :title="$t('page.resourceLibrary.resourceMigrationPreview')"
    :mask-closable="false"
  >
    <n-spin :show="migrationLoading">
      <template v-if="migrationPreview">
        <n-alert
          :type="migrationPreview.needs_review ? 'warning' : 'success'"
          class="mb-4"
        >
          {{
            $t("page.resourceLibrary.resourceMigrationSummary", {
              ready: migrationPreview.ready,
              review: migrationPreview.needs_review,
            })
          }}
        </n-alert>
        <n-data-table
          :columns="migrationPreviewColumns"
          :data="migrationPreview.items"
          :bordered="false"
          :max-height="420"
        />
      </template>
    </n-spin>
    <template #footer>
      <div class="flex justify-end gap-2">
        <n-button @click="migrationModalVisible = false">
          {{ $t("common.close") }}
        </n-button>
        <n-button
          type="primary"
          :disabled="!migrationPreview?.ready"
          :loading="migrationLoading"
          @click="runResourceMigration"
        >
          {{ $t("page.resourceLibrary.migrateReadyResources") }}
        </n-button>
      </div>
    </template>
  </n-modal>

  <n-modal v-model:show="scanModalVisible" preset="dialog" :title="$t('page.resourceLibrary.scan')" :show-icon="false">
    <n-alert type="info" class="mb-4">
      {{ $t("page.resourceLibrary.scanHint") }}
    </n-alert>
    <n-input v-model:value="scanCode" :placeholder="$t('page.resourceLibrary.scanPlaceholder')" />
    <video v-show="cameraActive" ref="cameraVideo" class="scanner-video mt-3" autoplay muted playsinline />
    <template #action>
      <n-button v-if="!cameraActive" secondary @click="startCameraScan">
        {{ $t("page.resourceLibrary.useCamera") }}
      </n-button>
      <n-button v-else secondary @click="stopCameraScan">
        {{ $t("page.resourceLibrary.stopCamera") }}
      </n-button>
      <n-button type="primary" :loading="scanLoading" @click="resolveScanCode">
        {{ $t("page.resourceLibrary.openScannedItem") }}
      </n-button>
    </template>
  </n-modal>

  <n-modal v-model:show="importModalVisible" preset="dialog" :title="$t('page.resourceLibrary.importResources')" :show-icon="false" class="resource-dialog">
    <n-alert type="info" class="mb-4">
      {{ $t("page.resourceLibrary.importHint") }}
    </n-alert>
    <n-form label-placement="top">
      <n-form-item :label="$t('page.resourceLibrary.resourceType')" required>
        <n-select v-model:value="importDraft.resource_type_id" :options="resourceTypeOptions" />
      </n-form-item>
      <n-form-item :label="$t('common.file')" required>
        <input type="file" accept=".csv,.tsv,.json,text/csv,text/tab-separated-values,application/json" @change="selectImportFile">
      </n-form-item>
      <div class="form-grid">
        <n-form-item :label="$t('page.resourceLibrary.nameColumn')">
          <n-input v-model:value="importDraft.name_field" />
        </n-form-item>
        <n-form-item :label="$t('page.resourceLibrary.codeColumn')">
          <n-input v-model:value="importDraft.code_field" />
        </n-form-item>
      </div>
      <n-form-item
        :label="$t('page.resourceLibrary.fieldMapping')"
        :feedback="importMappingError"
        :validation-status="importMappingError ? 'error' : undefined"
      >
        <n-input v-model:value="importDraft.field_mapping" type="textarea" :rows="4" placeholder="{&quot;CSV column&quot;: &quot;var.field&quot;}" />
      </n-form-item>
    </n-form>
    <n-alert v-if="importPreview" :type="importPreview.invalid ? 'warning' : 'success'" class="mb-3">
      {{ $t("page.resourceLibrary.importPreviewSummary", { valid: importPreview.valid, invalid: importPreview.invalid }) }}
    </n-alert>
    <n-data-table
      v-if="importPreview"
      :columns="importPreviewColumns"
      :data="importPreview.rows"
      :bordered="false"
      :max-height="260"
    />
    <template #action>
      <n-button :disabled="!importDraft.file || !importDraft.resource_type_id" :loading="importLoading" @click="previewImport">
        {{ $t("common.preview") }}
      </n-button>
      <n-button
        type="primary"
        :disabled="!importPreview || importPreview.invalid > 0"
        :loading="importLoading"
        @click="commitImport"
      >
        {{ $t("page.resourceLibrary.confirmImport") }}
      </n-button>
    </template>
  </n-modal>

  <n-modal v-model:show="inventoryModalVisible" preset="dialog" :title="$t('page.resourceLibrary.recordInventory')" :show-icon="false" class="resource-dialog">
    <n-form label-placement="top">
      <div class="form-grid">
        <n-form-item :label="$t('page.resourceLibrary.operation')" required>
          <n-select v-model:value="inventoryDraft.kind" :options="inventoryOperationOptions" />
        </n-form-item>
        <n-form-item :label="$t('page.resourceLibrary.resource')" required>
          <n-select v-model:value="inventoryDraft.resource_id" filterable :options="resourceOptions" />
        </n-form-item>
      </div>
      <n-form-item :label="$t('page.resourceLibrary.container')" required>
        <n-select v-model:value="inventoryDraft.container_id" :options="inventoryContainerOptions" />
      </n-form-item>
      <div class="form-grid">
        <n-form-item :label="inventoryDraft.kind === 'count' ? $t('page.resourceLibrary.countedBalance') : $t('page.resourceLibrary.quantity')" required>
          <n-input v-model:value="inventoryDraft.quantity" />
        </n-form-item>
        <n-form-item :label="$t('page.resourceLibrary.unit')" required>
          <n-input v-model:value="inventoryDraft.unit" placeholder="mL" />
        </n-form-item>
      </div>
      <n-form-item :label="$t('page.resourceLibrary.reason')">
        <n-input v-model:value="inventoryDraft.reason" type="textarea" />
      </n-form-item>
    </n-form>
    <template #action>
      <n-button @click="inventoryModalVisible = false">
        {{ $t("common.cancel") }}
      </n-button>
      <n-button type="primary" :loading="saving" @click="saveInventoryOperation">
        {{ $t("common.confirm") }}
      </n-button>
    </template>
  </n-modal>

  <n-modal v-model:show="transferModalVisible" preset="dialog" :title="$t('page.resourceLibrary.transferInventory')" :show-icon="false" class="resource-dialog">
    <n-form label-placement="top">
      <n-form-item :label="$t('page.resourceLibrary.resource')" required>
        <n-select v-model:value="transferDraft.resource_id" filterable :options="resourceOptions" />
      </n-form-item>
      <div class="form-grid">
        <n-form-item :label="$t('page.resourceLibrary.fromContainer')" required>
          <n-select v-model:value="transferDraft.from_container_id" :options="transferContainerOptions" />
        </n-form-item>
        <n-form-item :label="$t('page.resourceLibrary.toContainer')" required>
          <n-select v-model:value="transferDraft.to_container_id" :options="transferContainerOptions" />
        </n-form-item>
      </div>
      <div class="form-grid">
        <n-form-item :label="$t('page.resourceLibrary.quantity')" required>
          <n-input v-model:value="transferDraft.quantity" />
        </n-form-item>
        <n-form-item :label="$t('page.resourceLibrary.unit')" required>
          <n-input v-model:value="transferDraft.unit" />
        </n-form-item>
      </div>
      <n-form-item :label="$t('page.resourceLibrary.reason')">
        <n-input v-model:value="transferDraft.reason" type="textarea" />
      </n-form-item>
    </n-form>
    <template #action>
      <n-button @click="transferModalVisible = false">
        {{ $t("common.cancel") }}
      </n-button>
      <n-button type="primary" :loading="saving" @click="saveTransfer">
        {{ $t("common.confirm") }}
      </n-button>
    </template>
  </n-modal>

  <n-modal v-model:show="reservationModalVisible" preset="dialog" :title="$t('page.resourceLibrary.reserveInventory')" :show-icon="false" class="resource-dialog">
    <n-form label-placement="top">
      <n-form-item :label="$t('page.resourceLibrary.resource')" required>
        <n-select v-model:value="reservationDraft.resource_id" filterable :options="resourceOptions" />
      </n-form-item>
      <n-form-item :label="$t('page.resourceLibrary.container')" required>
        <n-select v-model:value="reservationDraft.container_id" :options="reservationContainerOptions" />
      </n-form-item>
      <div class="form-grid">
        <n-form-item :label="$t('page.resourceLibrary.quantity')" required>
          <n-input v-model:value="reservationDraft.quantity" />
        </n-form-item>
        <n-form-item :label="$t('page.resourceLibrary.unit')" required>
          <n-input v-model:value="reservationDraft.unit" />
        </n-form-item>
      </div>
      <n-form-item :label="$t('page.resourceLibrary.expiresAt')">
        <n-date-picker v-model:value="reservationDraft.expires_at" type="datetime" class="w-full" />
      </n-form-item>
      <n-form-item :label="$t('page.resourceLibrary.reason')">
        <n-input v-model:value="reservationDraft.reason" type="textarea" />
      </n-form-item>
    </n-form>
    <template #action>
      <n-button @click="reservationModalVisible = false">
        {{ $t("common.cancel") }}
      </n-button>
      <n-button type="primary" :loading="saving" @click="saveReservation">
        {{ $t("common.confirm") }}
      </n-button>
    </template>
  </n-modal>

  <n-drawer v-model:show="detailVisible" :width="560">
    <n-drawer-content :title="selectedResource?.name || $t('page.resourceLibrary.resourceDetail')" closable>
      <template v-if="selectedResource">
        <div class="mb-4 flex justify-end">
          <n-button secondary @click="openResourceRevision">
            {{ $t("page.resourceLibrary.reviseResource") }}
          </n-button>
        </div>
        <n-descriptions label-placement="left" :column="1" bordered>
          <n-descriptions-item :label="$t('page.resourceLibrary.stableCode')">
            {{ selectedResource.code }}
          </n-descriptions-item>
          <n-descriptions-item :label="$t('common.status')">
            {{ statusLabel(selectedResource.status) }}
          </n-descriptions-item>
          <n-descriptions-item :label="$t('page.resourceLibrary.visibility')">
            {{ selectedResource.visibility }}
          </n-descriptions-item>
          <n-descriptions-item :label="$t('page.resourceLibrary.schemaVersion')">
            {{ selectedResource.revision || "-" }}
          </n-descriptions-item>
        </n-descriptions>
        <h3 class="mt-6">
          {{ $t("page.resourceLibrary.customFields") }}
        </h3>
        <pre class="data-preview">{{ JSON.stringify(selectedResource.data || {}, null, 2) }}</pre>
        <n-collapse class="mt-5">
          <n-collapse-item :title="$t('page.resourceLibrary.revisionHistory')" name="revisions">
            <n-timeline>
              <n-timeline-item
                v-for="revision in selectedResource.revisions"
                :key="String(revision.id)"
                :title="`#${revision.revision} · ${revision.revision_kind}`"
                :content="String(revision.reason || '')"
                :time="formatDate(String(revision.created_at))"
              />
            </n-timeline>
          </n-collapse-item>
          <n-collapse-item :title="$t('page.resourceLibrary.relatedRecords')" name="records">
            <n-list v-if="selectedResource.record_links.length" bordered>
              <n-list-item v-for="link in selectedResource.record_links" :key="String(link.id)">
                <n-thing
                  :title="`${String(link.role || 'reference')} · Record ${String(link.record_id)}`"
                  :description="`v${String(link.record_version)} · ${String(link.protocol_version || '-')}`"
                />
              </n-list-item>
            </n-list>
            <n-empty v-else :description="$t('page.resourceLibrary.noRelatedRecords')" />
          </n-collapse-item>
          <n-collapse-item :title="$t('page.resourceLibrary.lineage')" name="lineage">
            <n-list v-if="selectedResource.lineage.length" bordered>
              <n-list-item v-for="edge in selectedResource.lineage" :key="String(edge.id)">
                <n-thing
                  :title="`${String(edge.parent_resource_id)} → ${String(edge.child_resource_id)}`"
                  :description="`${String(edge.relationship)} · Record ${String(edge.record_id)} v${String(edge.record_version)}`"
                />
              </n-list-item>
            </n-list>
            <n-empty v-else :description="$t('page.resourceLibrary.noLineage')" />
          </n-collapse-item>
          <n-collapse-item :title="$t('page.resourceLibrary.resourceAudit')" name="inventory-events">
            <n-timeline>
              <n-timeline-item
                v-for="event in selectedResource.inventory_events"
                :key="event.id"
                :title="`${event.kind} · ${event.quantity} ${event.unit}`"
                :content="event.reason"
                :time="formatDate(event.created_at)"
              />
            </n-timeline>
            <n-empty
              v-if="!selectedResource.inventory_events.length"
              :description="$t('page.resourceLibrary.noInventoryEvents')"
            />
          </n-collapse-item>
        </n-collapse>
        <div class="drawer-heading mt-6">
          <h3>{{ $t("page.resourceLibrary.inventoryContainers") }}</h3>
          <n-space>
            <n-button secondary size="small" @click="lotModalVisible = true">
              {{ $t("page.resourceLibrary.addLot") }}
            </n-button>
            <n-button secondary size="small" @click="containerModalVisible = true">
              {{ $t("page.resourceLibrary.addContainer") }}
            </n-button>
            <n-button secondary size="small" @click="openInventoryForResource(selectedResource)">
              {{ $t("page.resourceLibrary.recordInventory") }}
            </n-button>
            <n-button secondary size="small" @click="createLabelForResource">
              {{ $t("page.resourceLibrary.createLabel") }}
            </n-button>
          </n-space>
        </div>
        <n-data-table
          :columns="containerColumns"
          :data="selectedResource.containers || []"
          :bordered="false"
          :single-line="false"
          :max-height="260"
        />
        <div class="mt-6">
          <div class="drawer-heading">
            <h3>{{ $t("page.resourceLibrary.serviceHistory") }}</h3>
            <n-button secondary size="small" @click="serviceModalVisible = true">
              {{ $t("page.resourceLibrary.addServiceEvent") }}
            </n-button>
          </div>
          <n-timeline>
            <n-timeline-item
              v-for="event in selectedResource.equipment_service_events"
              :key="String(event.id)"
              :title="String(event.kind)"
              :content="String(event.notes || event.status || '')"
              :time="formatDate(String(event.starts_at))"
            />
          </n-timeline>
          <n-empty
            v-if="!selectedResource.equipment_service_events?.length"
            :description="$t('page.resourceLibrary.noServiceEvents')"
          />
        </div>
      </template>
    </n-drawer-content>
  </n-drawer>

  <n-modal
    v-model:show="resourceRevisionModalVisible"
    preset="dialog"
    :title="$t('page.resourceLibrary.reviseResource')"
    :show-icon="false"
  >
    <n-form label-placement="top">
      <n-form-item :label="$t('common.name')" required>
        <n-input v-model:value="resourceRevisionDraft.name" />
      </n-form-item>
      <div class="grid grid-cols-2 gap-4">
        <n-form-item :label="$t('common.status')" required>
          <n-select v-model:value="resourceRevisionDraft.status" :options="statusOptions" />
        </n-form-item>
        <n-form-item :label="$t('page.resourceLibrary.visibility')" required>
          <n-select
            v-model:value="resourceRevisionDraft.visibility"
            :options="[
              { label: $t('page.resourceLibrary.labVisible'), value: 'lab' },
              { label: $t('page.resourceLibrary.restricted'), value: 'restricted' },
            ]"
          />
        </n-form-item>
      </div>
      <n-form-item
        :label="$t('page.resourceLibrary.schemaData')"
        :validation-status="resourceRevisionJsonError ? 'error' : undefined"
        :feedback="resourceRevisionJsonError"
        required
      >
        <n-input v-model:value="resourceRevisionDraft.data" type="textarea" :rows="9" />
      </n-form-item>
      <n-form-item :label="$t('page.resourceLibrary.revisionReason')" required>
        <n-input v-model:value="resourceRevisionDraft.reason" type="textarea" />
      </n-form-item>
    </n-form>
    <template #action>
      <n-button @click="resourceRevisionModalVisible = false">
        {{ $t("common.cancel") }}
      </n-button>
      <n-button type="primary" :loading="saving" @click="saveResourceRevision">
        {{ $t("common.confirm") }}
      </n-button>
    </template>
  </n-modal>

  <n-modal v-model:show="lotModalVisible" preset="dialog" :title="$t('page.resourceLibrary.addLot')" :show-icon="false">
    <n-form label-placement="top">
      <n-form-item :label="$t('page.resourceLibrary.stableCode')" required>
        <n-input v-model:value="lotDraft.code" />
      </n-form-item>
      <n-form-item :label="$t('page.resourceLibrary.supplier')">
        <n-input v-model:value="lotDraft.supplier" />
      </n-form-item>
      <n-form-item :label="$t('page.resourceLibrary.expiresAt')">
        <n-date-picker v-model:value="lotDraft.expires_at" type="datetime" class="w-full" />
      </n-form-item>
    </n-form>
    <template #action>
      <n-button @click="lotModalVisible = false">{{ $t("common.cancel") }}</n-button>
      <n-button type="primary" :loading="saving" @click="saveLot">{{ $t("common.confirm") }}</n-button>
    </template>
  </n-modal>

  <n-modal v-model:show="containerModalVisible" preset="dialog" :title="$t('page.resourceLibrary.addContainer')" :show-icon="false">
    <n-form label-placement="top">
      <n-form-item :label="$t('page.resourceLibrary.stableCode')" required>
        <n-input v-model:value="containerDraft.code" />
      </n-form-item>
      <div class="form-grid">
        <n-form-item :label="$t('page.resourceLibrary.lot')">
          <n-select v-model:value="containerDraft.lot_id" clearable :options="selectedResourceLotOptions" />
        </n-form-item>
        <n-form-item :label="$t('page.resourceLibrary.location')">
          <n-select v-model:value="containerDraft.location_id" clearable :options="locationOptions" />
        </n-form-item>
      </div>
      <n-form-item :label="$t('page.resourceLibrary.unit')" required>
        <n-input v-model:value="containerDraft.unit" placeholder="mL" />
      </n-form-item>
    </n-form>
    <template #action>
      <n-button @click="containerModalVisible = false">{{ $t("common.cancel") }}</n-button>
      <n-button type="primary" :loading="saving" @click="saveContainer">{{ $t("common.confirm") }}</n-button>
    </template>
  </n-modal>

  <n-modal v-model:show="serviceModalVisible" preset="dialog" :title="$t('page.resourceLibrary.addServiceEvent')" :show-icon="false">
    <n-form label-placement="top">
      <div class="form-grid">
        <n-form-item :label="$t('page.resourceLibrary.serviceKind')" required>
          <n-select v-model:value="serviceDraft.kind" :options="serviceKindOptions" />
        </n-form-item>
        <n-form-item :label="$t('common.status')" required>
          <n-input v-model:value="serviceDraft.status" />
        </n-form-item>
      </div>
      <n-form-item :label="$t('page.resourceLibrary.start')" required>
        <n-date-picker v-model:value="serviceDraft.starts_at" type="datetime" class="w-full" />
      </n-form-item>
      <n-form-item :label="$t('page.resourceLibrary.dueAt')">
        <n-date-picker v-model:value="serviceDraft.due_at" type="datetime" class="w-full" />
      </n-form-item>
      <n-form-item :label="$t('page.resourceLibrary.notes')">
        <n-input v-model:value="serviceDraft.notes" type="textarea" />
      </n-form-item>
    </n-form>
    <template #action>
      <n-button @click="serviceModalVisible = false">{{ $t("common.cancel") }}</n-button>
      <n-button type="primary" :loading="saving" @click="saveServiceEvent">{{ $t("common.confirm") }}</n-button>
    </template>
  </n-modal>

  <n-modal v-model:show="labelModalVisible" preset="card" class="resource-label-modal" :title="$t('page.resourceLibrary.resourceLabel')">
    <div v-if="createdLabel" class="resource-label" id="resource-print-label">
      <n-qr-code v-if="createdLabel.format === 'qr'" :value="createdLabel.payload" :size="190" />
      <div v-else class="barcode-placeholder">
        <span>{{ createdLabel.code }}</span>
      </div>
      <strong>{{ selectedResource?.name }}</strong>
      <small>{{ selectedResource?.code }}</small>
      <code>{{ createdLabel.code }}</code>
    </div>
    <template #footer>
      <n-button type="primary" @click="printLabel">
        {{ $t("page.resourceLibrary.printLabel") }}
      </n-button>
    </template>
  </n-modal>

  <n-modal v-model:show="templateVisible" preset="card" class="resource-template-modal" :title="selectedTemplate?.name">
    <pre class="data-preview">{{ selectedTemplate?.aimd }}</pre>
  </n-modal>
</template>

<script setup lang="tsx">
import type {
  EquipmentBooking,
  InventoryEvent,
  InventoryReservation,
  ResourceDefinitionVersion,
  ResourceDetail,
  ResourceItem,
  ResourceLibrarySection,
  ResourceLocation,
  ResourceMigrationPreview,
  ResourceNotification,
  ResourceOverview,
  ResourceTemplate,
  ResourceType,
} from "@/service/api/resources"
import type { DataTableColumns } from "naive-ui"
import {
  commitResourceImport,
  createEquipmentBooking,
  createEquipmentServiceEvent,
  createInventoryReservation,
  createResource,
  createResourceContainer,
  createResourceLabel,
  createResourceLocation,
  createResourceLot,
  decideEquipmentBooking,
  dryRunResourceImport,
  fetchEquipmentBookings,
  fetchInventoryEvents,
  fetchInventoryReservations,
  fetchResource,
  fetchResourceDefinitionVersions,
  fetchResourceLocations,
  fetchResourceNotifications,
  fetchResourceOverview,
  fetchResources,
  fetchResourceTemplates,
  fetchResourceTypes,
  postInventoryOperation,
  previewResourceTypeMigration,
  readResourceNotification,
  registerResourceType,
  releaseInventoryReservation,
  resolveResourceLabel,
  reviseResource,
  reviseResourceType,
  startResourceTypeMigration,
  transferInventory,
} from "@/service/api/resources"
import { useLabInfoStore } from "@/views/labs/hooks/useLabsInfoStore"
import { $t } from "@airalogy/shared/locales"
import { NButton, NTag } from "naive-ui"

defineOptions({ name: "LabResourceLibrary" })

const route = useRoute()
const router = useRouter()
const { labInfo } = useLabInfoStore()!
const labId = computed(() => String(labInfo.value?.id || ""))

const sections = [
  { value: "overview" as const, label: $t("page.resourceLibrary.overview") },
  { value: "resources" as const, label: $t("page.resourceLibrary.resources") },
  { value: "inventory" as const, label: $t("page.resourceLibrary.inventory") },
  { value: "locations" as const, label: $t("page.resourceLibrary.locations") },
  { value: "bookings" as const, label: $t("page.resourceLibrary.bookings") },
  { value: "reminders" as const, label: $t("page.resourceLibrary.reminders") },
  { value: "events" as const, label: $t("page.resourceLibrary.events") },
  { value: "types" as const, label: $t("page.resourceLibrary.types") },
]
const activeSection = computed<ResourceLibrarySection>(() => {
  const section = String(route.params.section || "overview") as ResourceLibrarySection
  return sections.some(item => item.value === section) ? section : "overview"
})

const loading = ref(false)
const saving = ref(false)
const overview = reactive<ResourceOverview>({
  resources: 0,
  depleted: 0,
  expiring_within_30_days: 0,
  unread_notifications: 0,
  active_bookings: 0,
})
const resources = ref<ResourceItem[]>([])
const resourceTypes = ref<ResourceType[]>([])
const resourceDefinitionVersions = ref<ResourceDefinitionVersion[]>([])
const inventoryEvents = ref<InventoryEvent[]>([])
const reservations = ref<InventoryReservation[]>([])
const locations = ref<ResourceLocation[]>([])
const bookings = ref<EquipmentBooking[]>([])
const notifications = ref<ResourceNotification[]>([])
const templates = ref<ResourceTemplate[]>([])
const filters = reactive({ q: "", resourceTypeId: null as string | null, status: null as string | null })

const overviewCards = computed(() => [
  { key: "resources", label: $t("page.resourceLibrary.resources"), value: overview.resources, hint: $t("page.resourceLibrary.resourcesHint") },
  { key: "depleted", label: $t("page.resourceLibrary.depleted"), value: overview.depleted, hint: $t("page.resourceLibrary.depletedHint") },
  { key: "expiring", label: $t("page.resourceLibrary.expiring"), value: overview.expiring_within_30_days, hint: $t("page.resourceLibrary.expiringHint") },
  { key: "bookings", label: $t("page.resourceLibrary.activeBookings"), value: overview.active_bookings, hint: $t("page.resourceLibrary.activeBookingsHint") },
  { key: "reminders", label: $t("page.resourceLibrary.unreadReminders"), value: overview.unread_notifications, hint: $t("page.resourceLibrary.unreadRemindersHint") },
])
const resourceTypeOptions = computed(() => resourceTypes.value.map(item => ({ label: item.name, value: item.id })))
const resourceOptions = computed(() => resources.value.map(item => ({ label: `${item.name} · ${item.code}`, value: item.id })))
const locationOptions = computed(() => locations.value.map(item => ({ label: item.path, value: item.id })))
const equipmentOptions = computed(() => resources.value
  .filter(item => resourceTypes.value.find(type => type.id === item.resource_type_id)?.current_revision?.capabilities.booking)
  .map(item => ({ label: `${item.name} · ${item.code}`, value: item.id })))
const statusOptions = computed(() => ["active", "quarantined", "depleted", "retired"].map(value => ({ label: statusLabel(value), value })))
const bookingPolicyOptions = [
  { label: $t("page.resourceLibrary.bookingNone"), value: "none" },
  { label: $t("page.resourceLibrary.bookingAuto"), value: "auto" },
  { label: $t("page.resourceLibrary.bookingApproval"), value: "approval" },
  { label: $t("page.resourceLibrary.bookingAuthorized"), value: "authorized" },
]
const capabilityOptions = ["inventory", "lots", "containers", "expiry", "serial_number", "booking", "maintenance", "calibration"]
const inventoryOperationOptions = computed(() => [
  { label: $t("page.resourceLibrary.receipt"), value: "receipt" },
  { label: $t("page.resourceLibrary.consumption"), value: "consumption" },
  { label: $t("page.resourceLibrary.adjustment"), value: "adjustment" },
  { label: $t("page.resourceLibrary.physicalCount"), value: "count" },
  { label: $t("page.resourceLibrary.disposal"), value: "disposal" },
])

function formatDate(value?: string | null) {
  return value ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "-"
}

function statusLabel(value: string) {
  const key = `page.resourceLibrary.status.${value}` as const
  return $t(key as any)
}

const resourceColumns: DataTableColumns<ResourceItem> = [
  { title: $t("common.name"), key: "name", minWidth: 180 },
  { title: $t("page.resourceLibrary.stableCode"), key: "code", minWidth: 150 },
  {
    title: $t("page.resourceLibrary.resourceType"),
    key: "resource_type_id",
    minWidth: 150,
    render: row => resourceTypes.value.find(item => item.id === row.resource_type_id)?.name || "-",
  },
  {
    title: $t("common.status"),
    key: "status",
    width: 130,
    render: row => <NTag bordered={false} type={row.status === "active" ? "success" : row.status === "quarantined" ? "warning" : "default"}>{statusLabel(row.status)}</NTag>,
  },
  { title: $t("page.resourceLibrary.visibility"), key: "visibility", width: 120 },
  { title: $t("common.updateTime"), key: "updated_at", width: 180, render: row => formatDate(row.updated_at) },
]

const inventoryColumns: DataTableColumns<InventoryEvent> = [
  { title: $t("common.time"), key: "created_at", width: 180, render: row => formatDate(row.created_at) },
  { title: $t("page.resourceLibrary.operation"), key: "kind", width: 150 },
  { title: $t("page.resourceLibrary.resource"), key: "resource_id", minWidth: 180, ellipsis: { tooltip: true } },
  { title: $t("page.resourceLibrary.quantity"), key: "quantity", width: 150, render: row => `${row.quantity} ${row.unit}` },
  { title: $t("page.resourceLibrary.beforeAfter"), key: "on_hand_after", width: 180, render: row => `${row.on_hand_before ?? "-"} → ${row.on_hand_after ?? "-"}` },
  { title: $t("page.resourceLibrary.reason"), key: "reason", minWidth: 220 },
]

const locationColumns: DataTableColumns<ResourceLocation> = [
  { title: $t("common.name"), key: "name", minWidth: 180 },
  { title: $t("page.resourceLibrary.path"), key: "path", minWidth: 260 },
  { title: $t("page.resourceLibrary.locationKind"), key: "kind", width: 140 },
  { title: $t("page.resourceLibrary.visibility"), key: "visibility", width: 130 },
]

const bookingColumns: DataTableColumns<EquipmentBooking> = [
  { title: $t("page.resourceLibrary.equipment"), key: "resource_id", minWidth: 180, render: row => resources.value.find(item => item.id === row.resource_id)?.name || row.resource_id },
  { title: $t("page.resourceLibrary.start"), key: "starts_at", width: 180, render: row => formatDate(row.starts_at) },
  { title: $t("page.resourceLibrary.end"), key: "ends_at", width: 180, render: row => formatDate(row.ends_at) },
  { title: $t("page.resourceLibrary.purpose"), key: "purpose", minWidth: 180 },
  { title: $t("common.status"), key: "status", width: 120, render: row => <NTag bordered={false}>{row.status}</NTag> },
  {
    title: $t("common.action"),
    key: "actions",
    width: 180,
    render: row => row.status === "pending"
      ? (
          <div class="flex gap-2">
            <NButton text type="primary" onClick={() => decideBooking(row, "approve")}>
              {$t("common.approve")}
            </NButton>
            <NButton text type="error" onClick={() => decideBooking(row, "reject")}>
              {$t("common.reject")}
            </NButton>
          </div>
        )
      : null,
  },
]

const typeColumns: DataTableColumns<ResourceType> = [
  { title: $t("common.name"), key: "name", minWidth: 170 },
  { title: $t("page.resourceLibrary.stableCode"), key: "code", minWidth: 140 },
  { title: $t("page.resourceLibrary.protocolVersion"), key: "protocol_version", minWidth: 180, render: row => row.current_revision?.protocol_version || "-" },
  { title: $t("page.resourceLibrary.capabilities"), key: "capabilities", minWidth: 300, render: row => Object.keys(enabledCapabilities(row.current_revision?.capabilities || {})).join(" · ") || "-" },
  { title: $t("page.resourceLibrary.bookingPolicy"), key: "booking_policy", width: 150, render: row => row.current_revision?.booking_policy || "none" },
  {
    title: $t("common.action"),
    key: "actions",
    width: 110,
    fixed: "right",
    render: row => <NButton text type="primary" onClick={() => openResourceTypeUpgrade(row)}>{$t("page.resourceLibrary.upgradeType")}</NButton>,
  },
]

const containerColumns: DataTableColumns<Record<string, any>> = [
  { title: $t("page.resourceLibrary.container"), key: "code", minWidth: 150 },
  {
    title: $t("page.resourceLibrary.location"),
    key: "location_id",
    minWidth: 150,
    render: row => locations.value.find(item => item.id === row.location_id)?.path || row.location_id || "-",
  },
  {
    title: $t("page.resourceLibrary.available"),
    key: "available",
    width: 160,
    render: row => row.balance ? `${row.balance.available} ${row.balance.unit}` : "-",
  },
]

const reservationColumns: DataTableColumns<InventoryReservation> = [
  { title: $t("page.resourceLibrary.resource"), key: "resource_id", minWidth: 180, render: row => resources.value.find(item => item.id === row.resource_id)?.name || row.resource_id },
  { title: $t("page.resourceLibrary.container"), key: "container_id", minWidth: 180, ellipsis: { tooltip: true } },
  { title: $t("page.resourceLibrary.quantity"), key: "quantity", width: 150, render: row => `${row.quantity} ${row.unit}` },
  { title: $t("page.resourceLibrary.expiresAt"), key: "expires_at", width: 180, render: row => formatDate(row.expires_at) },
  { title: $t("common.status"), key: "status", width: 120, render: row => <NTag bordered={false}>{row.status}</NTag> },
  {
    title: $t("common.action"),
    key: "actions",
    width: 110,
    render: row => row.status === "active"
      ? <NButton text type="primary" onClick={() => releaseReservation(row)}>{$t("page.resourceLibrary.release")}</NButton>
      : null,
  },
]

type ImportPreview = Awaited<ReturnType<typeof dryRunResourceImport>>
const importPreviewColumns: DataTableColumns<ImportPreview["rows"][number]> = [
  { title: "#", key: "row", width: 60 },
  {
    title: $t("common.status"),
    key: "valid",
    width: 110,
    render: row => <NTag type={row.valid ? "success" : "error"} bordered={false}>{row.valid ? $t("page.resourceLibrary.valid") : $t("page.resourceLibrary.invalid")}</NTag>,
  },
  {
    title: $t("page.resourceLibrary.importIssues"),
    key: "issues",
    minWidth: 320,
    render: row => row.issues.map(item => `${item.path ? `${item.path}: ` : ""}${item.message}`).join("; ") || "-",
  },
]

const migrationPreviewColumns: DataTableColumns<ResourceMigrationPreview["items"][number]> = [
  { title: $t("page.resourceLibrary.resource"), key: "resource_id", minWidth: 220, ellipsis: { tooltip: true } },
  { title: $t("page.resourceLibrary.revision"), key: "resource_revision", width: 100 },
  {
    title: $t("common.status"),
    key: "status",
    width: 140,
    render: row => <NTag bordered={false} type={row.ready ? "success" : row.status === "already_current" ? "default" : "warning"}>{row.status}</NTag>,
  },
  {
    title: $t("page.resourceLibrary.importIssues"),
    key: "issues",
    minWidth: 280,
    render: row => row.issues.map(item => `${item.path ? `${item.path}: ` : ""}${item.message}`).join("; ") || (row.not_collected.length ? `not_collected: ${row.not_collected.join(", ")}` : "-"),
  },
]

function resourceRowProps(row: ResourceItem) {
  return { style: "cursor: pointer", onClick: () => openResource(row) }
}

async function navigateSection(section: ResourceLibrarySection) {
  await router.replace({
    name: "lab-resources",
    params: { labUid: route.params.labUid, section },
  })
}

async function loadResources() {
  if (!labId.value)
    return
  const response = await fetchResources(labId.value, {
    q: filters.q || undefined,
    resource_type_id: filters.resourceTypeId,
    status: filters.status,
    page_size: 100,
  })
  resources.value = response.items
}

async function loadSection() {
  if (!labId.value)
    return
  loading.value = true
  try {
    if (!resourceTypes.value.length)
      resourceTypes.value = (await fetchResourceTypes(labId.value)).items
    if (activeSection.value === "overview") {
      Object.assign(overview, await fetchResourceOverview(labId.value))
      await loadResources()
    }
    else if (activeSection.value === "resources") {
      await loadResources()
    }
    else if (activeSection.value === "inventory" || activeSection.value === "events") {
      inventoryEvents.value = (await fetchInventoryEvents(labId.value)).items
      if (activeSection.value === "inventory") {
        await loadResources()
        reservations.value = (await fetchInventoryReservations(labId.value)).items
        locations.value = (await fetchResourceLocations(labId.value)).items
      }
    }
    else if (activeSection.value === "locations") {
      locations.value = (await fetchResourceLocations(labId.value)).items
    }
    else if (activeSection.value === "bookings") {
      await loadResources()
      bookings.value = (await fetchEquipmentBookings(labId.value)).items
    }
    else if (activeSection.value === "reminders") {
      notifications.value = (await fetchResourceNotifications(labId.value)).items
    }
    else if (activeSection.value === "types") {
      const [types, templateResponse, definitions] = await Promise.all([
        fetchResourceTypes(labId.value),
        fetchResourceTemplates(labId.value),
        fetchResourceDefinitionVersions(labId.value),
      ])
      resourceTypes.value = types.items
      templates.value = templateResponse.templates
      resourceDefinitionVersions.value = definitions.items
    }
  }
  finally {
    loading.value = false
  }
}

const resourceModalVisible = ref(false)
const resourceJsonError = ref("")
const resourceDraft = reactive({
  resource_type_id: null as string | null,
  name: "",
  code: "",
  visibility: "lab" as "lab" | "restricted",
  data: "{\n  \n}",
})

async function saveResource() {
  if (!labId.value || !resourceDraft.resource_type_id || !resourceDraft.name || !resourceDraft.code)
    return
  let data: Record<string, unknown>
  try {
    data = JSON.parse(resourceDraft.data)
    resourceJsonError.value = ""
  }
  catch {
    resourceJsonError.value = $t("page.resourceLibrary.invalidJson")
    return
  }
  saving.value = true
  try {
    await createResource(labId.value, {
      resource_type_id: resourceDraft.resource_type_id,
      name: resourceDraft.name,
      code: resourceDraft.code,
      visibility: resourceDraft.visibility,
      data,
    })
    resourceModalVisible.value = false
    Object.assign(resourceDraft, { resource_type_id: null, name: "", code: "", visibility: "lab", data: "{\n  \n}" })
    await loadResources()
    window.$message?.success($t("page.resourceLibrary.resourceCreated"))
  }
  finally {
    saving.value = false
  }
}

const locationModalVisible = ref(false)
const locationDraft = reactive({ name: "", code: "", parent_id: null as string | null })
async function saveLocation() {
  if (!labId.value || !locationDraft.name || !locationDraft.code)
    return
  saving.value = true
  try {
    await createResourceLocation(labId.value, locationDraft)
    locationModalVisible.value = false
    Object.assign(locationDraft, { name: "", code: "", parent_id: null })
    locations.value = (await fetchResourceLocations(labId.value)).items
  }
  finally {
    saving.value = false
  }
}

const bookingModalVisible = ref(false)
const bookingDraft = reactive({ resource_id: null as string | null, range: null as [number, number] | null, purpose: "" })
async function saveBooking() {
  if (!labId.value || !bookingDraft.resource_id || !bookingDraft.range)
    return
  saving.value = true
  try {
    await createEquipmentBooking(labId.value, {
      resource_id: bookingDraft.resource_id,
      starts_at: new Date(bookingDraft.range[0]).toISOString(),
      ends_at: new Date(bookingDraft.range[1]).toISOString(),
      purpose: bookingDraft.purpose,
      idempotency_key: crypto.randomUUID(),
    })
    bookingModalVisible.value = false
    bookings.value = (await fetchEquipmentBookings(labId.value)).items
  }
  finally {
    saving.value = false
  }
}

async function decideBooking(row: EquipmentBooking, action: "approve" | "reject") {
  if (!labId.value)
    return
  await decideEquipmentBooking(labId.value, row.id, action)
  bookings.value = (await fetchEquipmentBookings(labId.value)).items
}

const typeModalVisible = ref(false)
const editingResourceType = ref<ResourceType | null>(null)
const resourceDefinitionOptions = computed(() => resourceDefinitionVersions.value
  .filter((item) => {
    const current = editingResourceType.value?.current_revision
    if (!current)
      return true
    return item.protocol_id === current.protocol_id
      && item.version.localeCompare(current.protocol_version, undefined, { numeric: true }) > 0
  })
  .map(item => ({
    label: `${item.protocol_name} · v${item.version} · ${item.project_name}${item.registered ? ` · ${$t("page.resourceLibrary.registered")}` : ""}`,
    value: item.id,
  })))
const typeDraft = reactive({
  protocol_version_id: "",
  name: "",
  code: "",
  capabilities: ["inventory", "containers"] as string[],
  booking_policy: "none",
})

function openNewResourceType() {
  editingResourceType.value = null
  Object.assign(typeDraft, {
    protocol_version_id: "",
    name: "",
    code: "",
    capabilities: ["inventory", "containers"],
    booking_policy: "none",
  })
  typeModalVisible.value = true
}

function openResourceTypeUpgrade(resourceType: ResourceType) {
  editingResourceType.value = resourceType
  const revision = resourceType.current_revision
  Object.assign(typeDraft, {
    protocol_version_id: "",
    name: resourceType.name,
    code: resourceType.code,
    capabilities: Object.keys(enabledCapabilities(revision?.capabilities || {})),
    booking_policy: revision?.booking_policy || "none",
  })
  typeModalVisible.value = true
}

const migrationModalVisible = ref(false)
const migrationLoading = ref(false)
const migrationPreview = ref<ResourceMigrationPreview | null>(null)
const migrationResourceTypeId = ref("")
const migrationIdempotencyKey = ref("")

async function saveResourceType() {
  if (!labId.value || !typeDraft.protocol_version_id || !typeDraft.name || !typeDraft.code)
    return
  saving.value = true
  try {
    const payload = {
      protocol_version_id: typeDraft.protocol_version_id,
      name: typeDraft.name,
      code: typeDraft.code,
      booking_policy: typeDraft.booking_policy,
      capabilities: Object.fromEntries(capabilityOptions.map(item => [item, typeDraft.capabilities.includes(item)])),
    }
    const upgrading = editingResourceType.value
    const saved = upgrading
      ? await reviseResourceType(labId.value, upgrading.id, payload)
      : await registerResourceType(labId.value, payload)
    typeModalVisible.value = false
    resourceTypes.value = (await fetchResourceTypes(labId.value)).items
    resourceDefinitionVersions.value = (await fetchResourceDefinitionVersions(labId.value)).items
    if (upgrading) {
      migrationResourceTypeId.value = saved.id
      migrationIdempotencyKey.value = crypto.randomUUID()
      migrationModalVisible.value = true
      migrationLoading.value = true
      try {
        migrationPreview.value = await previewResourceTypeMigration(
          labId.value,
          saved.id,
        )
      }
      finally {
        migrationLoading.value = false
      }
    }
  }
  finally {
    saving.value = false
  }
}

async function runResourceMigration() {
  if (
    !labId.value
    || !migrationResourceTypeId.value
    || !migrationPreview.value?.ready
  ) {
    return
  }
  migrationLoading.value = true
  try {
    await startResourceTypeMigration(
      labId.value,
      migrationResourceTypeId.value,
      migrationIdempotencyKey.value,
    )
    migrationModalVisible.value = false
    window.$message?.success($t("page.resourceLibrary.resourceMigrationQueued"))
  }
  finally {
    migrationLoading.value = false
  }
}

const detailVisible = ref(false)
const selectedResource = ref<ResourceDetail | null>(null)
async function openResource(row: ResourceItem) {
  detailVisible.value = true
  if (!labId.value)
    return
  const [resource, locationResponse] = await Promise.all([
    fetchResource(labId.value, row.id),
    locations.value.length
      ? Promise.resolve({ items: locations.value })
      : fetchResourceLocations(labId.value),
  ])
  selectedResource.value = resource
  locations.value = locationResponse.items
}

async function markNotificationRead(item: ResourceNotification) {
  if (!labId.value || item.read_at)
    return
  await readResourceNotification(labId.value, item.id)
  item.read_at = new Date().toISOString()
  overview.unread_notifications = Math.max(0, overview.unread_notifications - 1)
}

function enabledCapabilities(value: Record<string, boolean>) {
  return Object.fromEntries(Object.entries(value).filter(([, enabled]) => enabled))
}

const templateVisible = ref(false)
const selectedTemplate = ref<ResourceTemplate | null>(null)
function showTemplate(template: ResourceTemplate) {
  selectedTemplate.value = template
  templateVisible.value = true
}

function downloadTemplate(template: ResourceTemplate) {
  const url = URL.createObjectURL(
    new Blob([template.aimd], { type: "text/markdown;charset=utf-8" }),
  )
  const anchor = document.createElement("a")
  anchor.href = url
  anchor.download = `${template.id}.aimd`
  anchor.click()
  URL.revokeObjectURL(url)
}

const scanModalVisible = ref(false)
const scanCode = ref("")
const scanLoading = ref(false)
const cameraVideo = ref<HTMLVideoElement | null>(null)
const cameraActive = ref(false)
let cameraStream: MediaStream | null = null
let scanFrame = 0
function openScanModal() {
  scanModalVisible.value = true
}

const importModalVisible = ref(false)
const importLoading = ref(false)
const importPreview = ref<ImportPreview | null>(null)
const importMappingError = ref("")
const importDraft = reactive({
  resource_type_id: null as string | null,
  file: null as File | null,
  name_field: "name",
  code_field: "code",
  field_mapping: "",
})

function selectImportFile(event: Event) {
  importDraft.file = (event.target as HTMLInputElement).files?.[0] || null
  importPreview.value = null
}

function importOptions() {
  let field_mapping: Record<string, string> | undefined
  if (importDraft.field_mapping.trim()) {
    try {
      const parsed = JSON.parse(importDraft.field_mapping)
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed))
        throw new Error("Field mapping must be a JSON object")
      field_mapping = parsed
      importMappingError.value = ""
    }
    catch {
      importMappingError.value = $t("page.resourceLibrary.invalidFieldMapping")
      return null
    }
  }
  return {
    name_field: importDraft.name_field,
    code_field: importDraft.code_field,
    field_mapping,
  }
}

async function previewImport() {
  if (!labId.value || !importDraft.resource_type_id || !importDraft.file)
    return
  const options = importOptions()
  if (!options)
    return
  importLoading.value = true
  try {
    importPreview.value = await dryRunResourceImport(
      labId.value,
      importDraft.resource_type_id,
      importDraft.file,
      options,
    )
  }
  finally {
    importLoading.value = false
  }
}

async function commitImport() {
  if (!labId.value || !importDraft.resource_type_id || !importDraft.file || !importPreview.value || importPreview.value.invalid)
    return
  const options = importOptions()
  if (!options)
    return
  importLoading.value = true
  try {
    const result = await commitResourceImport(
      labId.value,
      importDraft.resource_type_id,
      importDraft.file,
      options,
    )
    window.$message?.success($t("page.resourceLibrary.importCompleted", { count: result.created }))
    importModalVisible.value = false
    importPreview.value = null
    importDraft.file = null
    await loadResources()
  }
  finally {
    importLoading.value = false
  }
}

const resourceRevisionModalVisible = ref(false)
const resourceRevisionJsonError = ref("")
const resourceRevisionDraft = reactive({
  name: "",
  status: "active",
  visibility: "lab" as "lab" | "restricted",
  data: "{}",
  reason: "",
})

function openResourceRevision() {
  if (!selectedResource.value)
    return
  Object.assign(resourceRevisionDraft, {
    name: selectedResource.value.name,
    status: selectedResource.value.status,
    visibility: selectedResource.value.visibility,
    data: JSON.stringify(selectedResource.value.data || {}, null, 2),
    reason: "",
  })
  resourceRevisionJsonError.value = ""
  resourceRevisionModalVisible.value = true
}

async function saveResourceRevision() {
  if (!labId.value || !selectedResource.value || !resourceRevisionDraft.name || !resourceRevisionDraft.reason)
    return
  let data: Record<string, unknown>
  try {
    const parsed = JSON.parse(resourceRevisionDraft.data)
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed))
      throw new Error("Resource data must be a JSON object")
    data = parsed
    resourceRevisionJsonError.value = ""
  }
  catch {
    resourceRevisionJsonError.value = $t("page.resourceLibrary.invalidJson")
    return
  }
  saving.value = true
  const resourceId = selectedResource.value.id
  try {
    await reviseResource(labId.value, resourceId, {
      name: resourceRevisionDraft.name,
      status: resourceRevisionDraft.status,
      visibility: resourceRevisionDraft.visibility,
      data,
      reason: resourceRevisionDraft.reason,
    })
    resourceRevisionModalVisible.value = false
    selectedResource.value = await fetchResource(labId.value, resourceId)
    await loadResources()
    window.$message?.success($t("page.resourceLibrary.resourceRevised"))
  }
  finally {
    saving.value = false
  }
}

const inventoryModalVisible = ref(false)
const inventoryResourceDetail = ref<ResourceDetail | null>(null)
const inventoryDraft = reactive({
  kind: "receipt" as "receipt" | "consumption" | "adjustment" | "count" | "disposal",
  resource_id: null as string | null,
  container_id: null as string | null,
  quantity: "",
  unit: "",
  reason: "",
})
const inventoryContainerOptions = computed(() =>
  (inventoryResourceDetail.value?.containers || []).map((item: any) => ({
    label: `${item.code} · ${item.balance?.available ?? "0"} ${item.balance?.unit || item.unit || ""}`,
    value: String(item.id),
  })),
)

watch(() => inventoryDraft.resource_id, async (resourceId) => {
  inventoryDraft.container_id = null
  inventoryResourceDetail.value = resourceId && labId.value
    ? await fetchResource(labId.value, resourceId)
    : null
  const first = inventoryResourceDetail.value?.containers?.[0] as any
  inventoryDraft.unit = String(first?.balance?.unit || first?.unit || "")
})

function openInventoryForResource(resource: ResourceDetail) {
  inventoryDraft.resource_id = resource.id
  detailVisible.value = false
  inventoryModalVisible.value = true
}

async function saveInventoryOperation() {
  if (!labId.value || !inventoryDraft.container_id || !inventoryDraft.quantity || !inventoryDraft.unit)
    return
  saving.value = true
  try {
    await postInventoryOperation(labId.value, inventoryDraft.kind, {
      container_id: inventoryDraft.container_id,
      quantity: inventoryDraft.quantity,
      unit: inventoryDraft.unit,
      reason: inventoryDraft.reason,
      idempotency_key: crypto.randomUUID(),
    })
    inventoryModalVisible.value = false
    Object.assign(inventoryDraft, { container_id: null, quantity: "", reason: "" })
    inventoryEvents.value = (await fetchInventoryEvents(labId.value)).items
    window.$message?.success($t("page.resourceLibrary.inventoryRecorded"))
  }
  finally {
    saving.value = false
  }
}

const transferModalVisible = ref(false)
const transferResourceDetail = ref<ResourceDetail | null>(null)
const transferDraft = reactive({
  resource_id: null as string | null,
  from_container_id: null as string | null,
  to_container_id: null as string | null,
  quantity: "",
  unit: "",
  reason: "",
})
const transferContainerOptions = computed(() =>
  (transferResourceDetail.value?.containers || []).map((item: any) => ({
    label: `${item.code} · ${item.balance?.available ?? "0"} ${item.balance?.unit || item.unit || ""}`,
    value: String(item.id),
  })),
)
watch(() => transferDraft.resource_id, async (resourceId) => {
  transferDraft.from_container_id = null
  transferDraft.to_container_id = null
  transferResourceDetail.value = resourceId && labId.value
    ? await fetchResource(labId.value, resourceId)
    : null
  const first = transferResourceDetail.value?.containers?.[0] as any
  transferDraft.unit = String(first?.balance?.unit || first?.unit || "")
})

async function saveTransfer() {
  if (
    !labId.value
    || !transferDraft.from_container_id
    || !transferDraft.to_container_id
    || !transferDraft.quantity
    || !transferDraft.unit
  ) {
    return
  }
  saving.value = true
  try {
    await transferInventory(labId.value, {
      from_container_id: transferDraft.from_container_id,
      to_container_id: transferDraft.to_container_id,
      quantity: transferDraft.quantity,
      unit: transferDraft.unit,
      reason: transferDraft.reason,
      idempotency_key: crypto.randomUUID(),
    })
    transferModalVisible.value = false
    inventoryEvents.value = (await fetchInventoryEvents(labId.value)).items
    window.$message?.success($t("page.resourceLibrary.inventoryTransferred"))
  }
  finally {
    saving.value = false
  }
}

const reservationModalVisible = ref(false)
const reservationResourceDetail = ref<ResourceDetail | null>(null)
const reservationDraft = reactive({
  resource_id: null as string | null,
  container_id: null as string | null,
  quantity: "",
  unit: "",
  expires_at: null as number | null,
  reason: "",
})
const reservationContainerOptions = computed(() =>
  (reservationResourceDetail.value?.containers || []).map((item: any) => ({
    label: `${item.code} · ${item.balance?.available ?? "0"} ${item.balance?.unit || item.unit || ""}`,
    value: String(item.id),
  })),
)
watch(() => reservationDraft.resource_id, async (resourceId) => {
  reservationDraft.container_id = null
  reservationResourceDetail.value = resourceId && labId.value
    ? await fetchResource(labId.value, resourceId)
    : null
  const first = reservationResourceDetail.value?.containers?.[0] as any
  reservationDraft.unit = String(first?.balance?.unit || first?.unit || "")
})

async function saveReservation() {
  if (
    !labId.value
    || !reservationDraft.resource_id
    || !reservationDraft.container_id
    || !reservationDraft.quantity
    || !reservationDraft.unit
  ) {
    return
  }
  saving.value = true
  try {
    await createInventoryReservation(labId.value, {
      resource_id: reservationDraft.resource_id,
      container_id: reservationDraft.container_id,
      quantity: reservationDraft.quantity,
      unit: reservationDraft.unit,
      expires_at: reservationDraft.expires_at
        ? new Date(reservationDraft.expires_at).toISOString()
        : undefined,
      reason: reservationDraft.reason,
      idempotency_key: crypto.randomUUID(),
    })
    reservationModalVisible.value = false
    reservations.value = (await fetchInventoryReservations(labId.value)).items
    window.$message?.success($t("page.resourceLibrary.inventoryReserved"))
  }
  finally {
    saving.value = false
  }
}

async function releaseReservation(reservation: InventoryReservation) {
  if (!labId.value)
    return
  await releaseInventoryReservation(
    labId.value,
    reservation.id,
    crypto.randomUUID(),
  )
  reservations.value = (await fetchInventoryReservations(labId.value)).items
}

const lotModalVisible = ref(false)
const lotDraft = reactive({
  code: "",
  supplier: "",
  expires_at: null as number | null,
})
const containerModalVisible = ref(false)
const containerDraft = reactive({
  code: "",
  lot_id: null as string | null,
  location_id: null as string | null,
  unit: "",
})
const selectedResourceLotOptions = computed(() =>
  (selectedResource.value?.lots || []).map((item: any) => ({
    label: String(item.code || item.id),
    value: String(item.id),
  })),
)

async function refreshSelectedResource() {
  if (labId.value && selectedResource.value) {
    selectedResource.value = await fetchResource(
      labId.value,
      selectedResource.value.id,
    )
  }
}

async function saveLot() {
  if (!labId.value || !selectedResource.value || !lotDraft.code)
    return
  saving.value = true
  try {
    await createResourceLot(labId.value, selectedResource.value.id, {
      code: lotDraft.code,
      supplier: lotDraft.supplier || undefined,
      expires_at: lotDraft.expires_at
        ? new Date(lotDraft.expires_at).toISOString()
        : undefined,
    })
    lotModalVisible.value = false
    Object.assign(lotDraft, { code: "", supplier: "", expires_at: null })
    await refreshSelectedResource()
  }
  finally {
    saving.value = false
  }
}

async function saveContainer() {
  if (
    !labId.value
    || !selectedResource.value
    || !containerDraft.code
    || !containerDraft.unit
  ) {
    return
  }
  saving.value = true
  try {
    await createResourceContainer(labId.value, selectedResource.value.id, {
      code: containerDraft.code,
      lot_id: containerDraft.lot_id,
      location_id: containerDraft.location_id,
      unit: containerDraft.unit,
    })
    containerModalVisible.value = false
    Object.assign(containerDraft, {
      code: "",
      lot_id: null,
      location_id: null,
      unit: "",
    })
    await refreshSelectedResource()
  }
  finally {
    saving.value = false
  }
}

const serviceModalVisible = ref(false)
const serviceKindOptions = ["calibration", "maintenance", "fault", "decommission"]
  .map(value => ({ label: value, value }))
const serviceDraft = reactive({
  kind: "maintenance" as "calibration" | "maintenance" | "fault" | "decommission",
  status: "scheduled",
  starts_at: Date.now() as number | null,
  due_at: null as number | null,
  notes: "",
})

async function saveServiceEvent() {
  if (!labId.value || !selectedResource.value || !serviceDraft.starts_at)
    return
  saving.value = true
  try {
    await createEquipmentServiceEvent(labId.value, {
      resource_id: selectedResource.value.id,
      kind: serviceDraft.kind,
      status: serviceDraft.status,
      starts_at: new Date(serviceDraft.starts_at).toISOString(),
      due_at: serviceDraft.due_at
        ? new Date(serviceDraft.due_at).toISOString()
        : undefined,
      notes: serviceDraft.notes,
    })
    serviceModalVisible.value = false
    await refreshSelectedResource()
  }
  finally {
    saving.value = false
  }
}

const labelModalVisible = ref(false)
const createdLabel = ref<Awaited<ReturnType<typeof createResourceLabel>> | null>(null)
async function createLabelForResource() {
  if (!labId.value || !selectedResource.value)
    return
  createdLabel.value = await createResourceLabel(labId.value, {
    target_type: "resource",
    target_id: selectedResource.value.id,
    format: "qr",
  })
  labelModalVisible.value = true
}

function printLabel() {
  window.print()
}

function normalizedScanCode(value: string) {
  const trimmed = value.trim()
  return trimmed.startsWith("airalogy://resource-label/")
    ? trimmed.split("/").pop() || ""
    : trimmed
}

async function resolveScanCode() {
  const code = normalizedScanCode(scanCode.value)
  if (!labId.value || !code)
    return
  scanLoading.value = true
  try {
    const label = await resolveResourceLabel(labId.value, code)
    stopCameraScan()
    scanModalVisible.value = false
    if (label.target_type === "resource" || label.target_type === "equipment") {
      await openResource({ id: label.target_id } as ResourceItem)
    }
    else {
      await navigateSection(label.target_type === "location" ? "locations" : "inventory")
    }
  }
  finally {
    scanLoading.value = false
  }
}

async function startCameraScan() {
  const BarcodeDetector = (window as any).BarcodeDetector
  if (!BarcodeDetector || !navigator.mediaDevices?.getUserMedia) {
    window.$message?.warning($t("page.resourceLibrary.cameraUnavailable"))
    return
  }
  cameraStream = await navigator.mediaDevices.getUserMedia({
    video: { facingMode: "environment" },
  })
  cameraActive.value = true
  await nextTick()
  if (cameraVideo.value)
    cameraVideo.value.srcObject = cameraStream
  const detector = new BarcodeDetector({ formats: ["qr_code", "code_128", "code_39"] })
  const detect = async () => {
    if (!cameraActive.value || !cameraVideo.value)
      return
    try {
      const results = await detector.detect(cameraVideo.value)
      if (results[0]?.rawValue) {
        scanCode.value = results[0].rawValue
        await resolveScanCode()
        return
      }
    }
    catch {
      // A video frame may not be ready yet; keep scanning.
    }
    scanFrame = requestAnimationFrame(detect)
  }
  scanFrame = requestAnimationFrame(detect)
}

function stopCameraScan() {
  cameraActive.value = false
  cancelAnimationFrame(scanFrame)
  cameraStream?.getTracks().forEach(track => track.stop())
  cameraStream = null
  if (cameraVideo.value)
    cameraVideo.value.srcObject = null
}

watch(scanModalVisible, (visible) => {
  if (!visible)
    stopCameraScan()
})

function exportInventory() {
  const header = ["time", "kind", "resource_id", "quantity", "unit", "before", "after", "reason"]
  const lines = inventoryEvents.value.map(item => [
    item.created_at,
    item.kind,
    item.resource_id,
    item.quantity,
    item.unit,
    item.on_hand_before || "",
    item.on_hand_after || "",
    item.reason,
  ].map(value => JSON.stringify(value)).join(","))
  const blob = new Blob([[header.join(","), ...lines].join("\n")], { type: "text/csv;charset=utf-8" })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement("a")
  anchor.href = url
  anchor.download = `airalogy-inventory-${new Date().toISOString().slice(0, 10)}.csv`
  anchor.click()
  URL.revokeObjectURL(url)
}

watch([labId, activeSection], loadSection, { immediate: true })
</script>

<style scoped>
.resource-library {
  min-height: 36rem;
  padding: 4px 0 40px;
}

.resource-library__hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  padding: 8px 0 22px;
}

.resource-library__hero h2 {
  margin: 2px 0 6px;
  color: #17243a;
  font-size: 28px;
}

.resource-library__hero p {
  max-width: 760px;
  margin: 0;
  color: #667085;
}

.resource-library__eyebrow {
  color: #1768c5 !important;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: .1em;
  text-transform: uppercase;
}

.resource-library__tabs {
  margin-bottom: 20px;
}

.resource-library__panel,
.metric-card,
.template-card {
  border: 1px solid #e7ebf2;
  border-radius: 14px;
  background: #fff;
}

.resource-library__panel {
  padding: 20px;
}

.metric-card {
  min-height: 132px;
  padding: 18px;
  background: linear-gradient(145deg, #fff 20%, #f5f9ff 100%);
}

.metric-card span,
.metric-card small {
  display: block;
  color: #667085;
}

.metric-card strong {
  display: block;
  margin: 8px 0 5px;
  color: #175fae;
  font-size: 30px;
}

.panel-heading,
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 18px;
}

.panel-heading {
  justify-content: space-between;
}

.panel-heading h3,
.panel-heading p {
  margin: 0;
}

.panel-heading p {
  margin-top: 4px;
  color: #7b8494;
}

.notification-list {
  display: grid;
  gap: 10px;
}

.notification-item {
  display: grid;
  grid-template-columns: 8px minmax(0, 1fr) auto;
  align-items: center;
  gap: 14px;
  width: 100%;
  padding: 16px;
  border: 1px solid #edf0f5;
  border-radius: 10px;
  background: #fff;
  text-align: left;
}

.notification-item--unread {
  border-color: #b9d8fa;
  background: #f5faff;
}

.notification-item__dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #b7bec9;
}

.notification-item--unread .notification-item__dot {
  background: #1770d3;
}

.notification-item strong,
.notification-item small {
  display: block;
}

.notification-item small,
.notification-item time {
  margin-top: 3px;
  color: #7b8494;
}

.template-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 14px;
}

.template-card {
  display: grid;
  gap: 14px;
  padding: 18px;
}

.template-card small {
  display: block;
  margin-top: 3px;
  color: #7b8494;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}

.data-preview {
  overflow: auto;
  max-height: 50vh;
  margin-top: 12px;
  padding: 16px;
  border-radius: 10px;
  background: #f6f8fb;
  color: #344054;
  white-space: pre-wrap;
}

.drawer-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.scanner-video {
  width: 100%;
  max-height: 320px;
  border-radius: 10px;
  background: #111827;
}

.resource-label {
  display: grid;
  justify-items: center;
  gap: 8px;
  padding: 24px;
  border: 1px solid #d9dee8;
  border-radius: 12px;
  background: #fff;
  text-align: center;
}

.resource-label strong {
  font-size: 20px;
}

.resource-label small,
.resource-label code {
  color: #667085;
}

.barcode-placeholder {
  display: grid;
  place-items: end center;
  width: 280px;
  height: 96px;
  padding-bottom: 8px;
  background: repeating-linear-gradient(90deg, #111 0 2px, transparent 2px 5px, #111 5px 6px, transparent 6px 9px);
}

.barcode-placeholder span {
  padding: 2px 8px;
  background: #fff;
  font-family: monospace;
}

:global(.resource-dialog) {
  width: min(680px, calc(100vw - 32px));
}

:global(.resource-template-modal) {
  width: min(820px, calc(100vw - 32px));
}

:global(.resource-migration-modal) {
  width: min(960px, calc(100vw - 32px));
}

:global(.resource-label-modal) {
  width: min(430px, calc(100vw - 32px));
}

@media print {
  :global(body *) {
    visibility: hidden;
  }

  :global(#resource-print-label),
  :global(#resource-print-label *) {
    visibility: visible;
  }

  :global(#resource-print-label) {
    position: fixed;
    inset: 0 auto auto 0;
    width: 90mm;
  }
}

@media (max-width: 720px) {
  .resource-library__hero,
  .toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>

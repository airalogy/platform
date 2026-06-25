<template>
  <div class="flex items-center">
    <slot v-if="showIcon" :icon-size="iconSize" name="prefix-icon">
      <protocol-icon class="mr-5" :size="iconSize" />
    </slot>

    <template v-if="protocolInfo">
      <div :class="props.contentClass" class="flex flex-1 items-center gap-x-3 overflow-hidden">
        <!-- Map through breadcrumb sections -->
        <template v-for="(section, index) in visibleSections" :key="section.id">
          <!-- Separator between sections -->
          <span v-if="index > 0 && !section.hideSeparator" class="select-none color-text-secondary" :class="separatorSize">
            /
          </span>

          <!-- Section content with tooltip -->
          <component :is="section.isPopup ? NPopover : NTooltip" trigger="hover" :class="section.isPopup && '!p-0'">
            <template #trigger>
              <router-link
                v-if="section.link"
                :to="section.link"
                class="flex-shrink-1 ellipsis-text color-text-secondary"
                :class="textSize"
              >
                {{ section.text }}
              </router-link>
              <h2 v-else-if="typeof section.text === 'string'" class="flex-shrink-1 ellipsis-text" :class="textSize">
                {{ section.text }}
              </h2>
              <component :is="section.text" v-else />
            </template>
            <!-- {{ section.tooltip }} -->
            <template v-if="typeof section.tooltip === 'string'">
              {{ section.tooltip }}
            </template>
            <component :is="section.tooltip" v-else-if="section.tooltip" />
          </component>
        </template>

        <n-tooltip v-if="showVersion && showCurrentVersion && protocolInfo?.metadata?.version">
          <template #trigger>
            <n-tag type="success" size="small">
              v{{ protocolInfo?.metadata?.version }}
            </n-tag>
          </template>
          Latest version: v{{ protocolInfo.latest_version }}
        </n-tooltip>
        <n-tag v-else-if="showVersion && !showCurrentVersion && protocolInfo?.latest_version" type="success" size="small">
          v{{ protocolInfo.latest_version }}
        </n-tag>
      </div>
    </template>
    <n-skeleton v-else width="20rem" />
    <slot name="actions" />
  </div>
</template>

<script setup lang="ts">
import type { ProtocolModels } from "@airalogy/shared/types"
import type { Component } from "vue"
import type { RouteLocationRaw } from "vue-router"
import { CopyToClip } from "@airalogy/components"
import { getAiralogyIds } from "@airalogy/shared/utils"
import { NPopover, NSkeleton, NTooltip } from "naive-ui"
import { computed } from "vue"

defineOptions({
  name: "ProtocolTitleSection",
})

const props = withDefaults(defineProps<Props>(), {
  protocolInfo: null,
  title: "",
  showIcon: true,
  showLabInfo: true,
  showProjectInfo: true,
  size: "medium",
  contentClass: "",
  showCurrentVersion: true,
  showVersion: true,
})

interface Props {
  /** Protocol information object */
  protocolInfo?: ProtocolModels.ProjectProtocolInfo | null
  /** Title text to display */
  title?: string
  /** Whether to display the research icon */
  showIcon?: boolean
  /** Whether to display lab information */
  showLabInfo?: boolean
  /** Whether to display project information */
  showProjectInfo?: boolean
  /** Size of the title section */
  size?: "tiny" | "small" | "medium" | "large"
  /** Class for the content container */
  contentClass?: string
  /** Breadcrumb sections */
  breadcrumbs?: BreadcrumbSection[]
  /** Whether to display the protocol link */
  isProtocolLink?: boolean
  /** Whether to display version tags */
  showVersion?: boolean
  /** Whether to display the current version (if false, shows latest version) */
  showCurrentVersion?: boolean
}

export interface BreadcrumbSection {
  id: string
  text: string | Component
  link?: RouteLocationRaw
  visible: boolean
  hideSeparator?: boolean
  tooltip?: string | Component
  isPopup?: boolean
}

const iconSize = computed(() => {
  switch (props.size) {
    case "tiny":
      return 24
    case "small":
      return 32
    case "medium":
      return 40
    case "large":
      return 48
    default:
      return 32
  }
})

const textSize = computed(() => {
  switch (props.size) {
    case "tiny":
      return "text-3.5"
    case "small":
      return "text-4.5"
    case "medium":
      return "text-6"
    case "large":
      return "text-7"
    default:
      return "text-5"
  }
})

const separatorSize = computed(() => {
  switch (props.size) {
    case "tiny":
      return "text-3"
    case "small":
      return "text-4.5"
    case "medium":
      return "text-6"
    case "large":
      return "text-7"
    default:
      return "text-5"
  }
})

// Create breadcrumb sections array
const breadcrumbSections = computed<BreadcrumbSection[]>(() => {
  const { protocolInfo, showLabInfo, showProjectInfo, title, isProtocolLink } = props
  if (!protocolInfo) {
    return props.breadcrumbs || []
  }

  const { lab, project, name, uid } = protocolInfo
  const { lab: labId, project: projectId, protocol: protocolId } = getAiralogyIds(protocolInfo) || {}
  return [
    {
      id: "lab",
      text: lab.name || "",
      link: { name: "lab-projects", params: { labUid: lab.uid } },
      visible: showLabInfo && !!lab.name,
      tooltip: labId ? () => h(CopyToClip, { text: labId, showSuccess: true, color: "#ffffff" }) : undefined,
    },
    {
      id: "project",
      text: project.name || "",
      link: {
        name: "project-protocols",
        params: {
          labUid: lab.uid,
          projectUid: project.uid,
        },
      },
      visible: showProjectInfo && !!project.name,
      tooltip: projectId ? () => h(CopyToClip, { text: projectId, showSuccess: true, color: "#ffffff" }) : undefined,
    },
    {
      id: "title",
      text: title || name || "",
      visible: !!(title || name),
      tooltip: protocolId ? () => h(CopyToClip, { text: protocolId, showSuccess: true, color: "#ffffff" }) : undefined,
      link: isProtocolLink ? { name: "protocol-info", params: { protocolUid: uid } } : undefined,
    },
    ...(props.breadcrumbs || []),
  ]
})

const visibleSections = useArrayFilter(breadcrumbSections, section => section.visible)
</script>

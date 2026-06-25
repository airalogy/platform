import type { MaybeRefOrGetter } from "vue"
import { LabRole, ProjectRole, ProjectType } from "@/enum"
import { $t } from "../locales"

export interface RoleInfo {
  label: string
  value: ProjectRole | LabRole
  description: string
  permissions: string[]
}
function getProjectRoleDetailsPrivate(): Partial<Record<ProjectRole, RoleInfo>> {
  return {
    [ProjectRole.OWNER]: {
      label: $t("role.owner"),
      value: ProjectRole.OWNER,
      description: $t("role.description.project.owner"),
      permissions: [$t("role.permission.project.owner.setManager")],
    },
    [ProjectRole.MANAGER]: {
      label: $t("role.manager"),
      value: ProjectRole.MANAGER,
      description: $t("role.description.project.manager"),
      permissions: [
        $t("role.permission.project.manager.assignRole"),
        $t("role.permission.project.manager.manageProtocols"),
        $t("role.permission.project.manager.deleteOwnRecords"),
        $t("role.permission.project.manager.deleteOthersRecords"),
      ],
    },
    [ProjectRole.COLLABORATOR]: {
      label: $t("role.collaborator"),
      value: ProjectRole.COLLABORATOR,
      description: $t("role.description.project.collaborator"),
      permissions: [
        $t("role.permission.project.collaborator.createProtocol"),
        $t("role.permission.project.collaborator.manageOwnProtocol"),
        $t("role.permission.project.collaborator.viewOthersRecords"),
      ],
    },
    [ProjectRole.RECORDER]: {
      label: $t("role.recorder"),
      value: ProjectRole.RECORDER,
      description: $t("role.description.project.recorder"),
      permissions: [
        $t("role.permission.project.recorder.createProtocol"),
        $t("role.permission.project.recorder.manageOwnProtocol"),
        $t("role.permission.project.recorder.submitRecords"),
        $t("role.permission.project.recorder.viewOwnRecords"),
      ],
    },
  }
}

export function getProjectRoleDetailsPublic(): Partial<Record<ProjectRole, RoleInfo>> {
  return {
    ...getProjectRoleDetailsPrivate(),
    [ProjectRole.RECORDER]: {
      label: $t("role.recorder"),
      value: ProjectRole.RECORDER,
      description: $t("role.description.project.recorderPublic"),
      permissions: [
        $t("role.permission.project.explorer.openDataEntry"),
        $t("role.permission.project.recorder.submitRecords"),
        $t("role.permission.project.recorder.viewOwnRecords"),
        $t("role.permission.project.collaborator.viewOthersRecords"),
      ],
    },
    [ProjectRole.RECORDER_SELF_ONLY]: {
      label: $t("role.recorder_self_only"),
      value: ProjectRole.RECORDER_SELF_ONLY,
      description: $t("role.description.project.recorderSelfOnly"),
      permissions: [],
    },
    [ProjectRole.EXPLORER]: {
      label: $t("role.explorer"),
      value: ProjectRole.EXPLORER,
      description: $t("role.description.project.explorer"),
      permissions: [$t("role.permission.project.explorer.openDataEntry")],
    },
    [ProjectRole.EXPLORER_SELF_ONLY]: {
      label: $t("role.explorer_self_only"),
      value: ProjectRole.EXPLORER_SELF_ONLY,
      description: $t("role.description.project.explorerSelfOnly"),
      permissions: [],
    },
    [ProjectRole.VIEWER]: {
      label: $t("role.viewer"),
      value: ProjectRole.VIEWER,
      description: $t("role.description.project.viewer"),
      permissions: [$t("role.permission.project.viewer.previewPublicProtocols")],
    },
    [ProjectRole.VIEWER_SELF_ONLY]: {
      label: $t("role.viewer_self_only"),
      value: ProjectRole.VIEWER_SELF_ONLY,
      description: $t("role.description.project.viewerSelfOnly"),
      permissions: [],
    },
  }
}

export const projectRoleHierarchyPrivate = [
  ProjectRole.RECORDER_SELF_ONLY,
  ProjectRole.RECORDER,
  ProjectRole.COLLABORATOR,
  ProjectRole.MANAGER,
  ProjectRole.OWNER,
]
export const projectRoleHierarchyPublic = [
  ProjectRole.VIEWER_SELF_ONLY,
  ProjectRole.VIEWER,
  ProjectRole.EXPLORER_SELF_ONLY,
  ProjectRole.EXPLORER,
  ...projectRoleHierarchyPrivate,
]

export function getProjectRoleInfo(role: ProjectRole, type: ProjectType): RoleInfo[] {
  const roleHierarchy = type === ProjectType.PRIVATE ? projectRoleHierarchyPrivate : projectRoleHierarchyPublic
  const roleDetails = type === ProjectType.PRIVATE ? getProjectRoleDetailsPrivate() : getProjectRoleDetailsPublic()

  return getRoleInfo(roleHierarchy, roleDetails, role)
}
export const labRoleHierarchy = [
  LabRole.MEMBER,
  LabRole.MANAGER,
  LabRole.OWNER,
]
function getLabRoleDetails(): Partial<Record<LabRole, RoleInfo>> {
  return {
    [LabRole.OWNER]: {
      label: $t("role.owner"),
      value: LabRole.OWNER,
      description: $t("role.description.lab.owner"),
      permissions: [$t("role.permission.lab.owner.setManager")],
    },
    [LabRole.MANAGER]: {
      label: $t("role.manager"),
      value: LabRole.MANAGER,
      description: $t("role.description.lab.manager"),
      permissions: [
        $t("role.permission.lab.manager.assignRole"),
        $t("role.permission.lab.manager.manageGroups"),
        $t("role.permission.lab.manager.deleteOwnRecords"),
        $t("role.permission.lab.manager.deleteOthersRecords"),
      ],
    },
    [LabRole.MEMBER]: {
      label: $t("role.member"),
      value: LabRole.MEMBER,
      description: $t("role.description.lab.member"),
      permissions: [
        $t("role.permission.lab.member.createProject"),
        $t("role.permission.lab.member.manageOwnProject"),
        $t("role.permission.lab.member.viewOthersProtocols"),
      ],
    },
  }
}

export function getLabRoleInfo(role: LabRole): RoleInfo[] {
  return getRoleInfo(labRoleHierarchy, getLabRoleDetails(), role)
}
export function getRoleLabel(role: ProjectRole | LabRole, type: "lab" | "project" | "group") {
  if (type === "group" || type === "project") {
    return getProjectRoleDetailsPublic()[role as ProjectRole]?.label || null
  }
  else if (type === "lab") {
    return getLabRoleDetails()[role as LabRole]?.label || null
  }

  return null
}
export function getRoleInfo<T extends ProjectRole | LabRole>(hierarchy: T[], details: Partial<Record<T, RoleInfo>>, role: T): RoleInfo[] {
  const roleIndex = hierarchy.indexOf(role)
  if (roleIndex === -1) {
    return []
  }

  const list: RoleInfo[] = []
  for (let i = roleIndex; i >= 0; i--) {
    const currentRole = hierarchy[i]
    const roleInfo = details[currentRole]
    if (roleInfo) {
      list.push(roleInfo)
    }
  }

  return list
}
export function useRoleDescription(roleRef: MaybeRefOrGetter<ProjectRole | LabRole>, typeRef: MaybeRefOrGetter<"lab" | "project" | "group">, projectType?: MaybeRefOrGetter<ProjectType>, modify = false) {
  const roleLabel = computed<string | null>(() => {
    const role = toValue(roleRef)
    const type = toValue(typeRef)

    return getRoleLabel(role, type)
  })

  const color = computed(() => {
    const role = toValue(roleRef)
    const type = toValue(typeRef)

    if (type === "lab") {
      switch (role) {
        case LabRole.OWNER:
          return { color: "#FFF1F0", textColor: "#F5222D" }
        case LabRole.MANAGER:
          return { color: "#FFF7EF", textColor: "#F99534" }
        case LabRole.MEMBER:
          return { color: "#EDF8F4", textColor: "#1BA37B" }
      }
    }

    if (type === "project" || type === "group") {
      switch (role) {
        case ProjectRole.OWNER:
          return { color: "#FFF1F0", textColor: "#F5222D" }
        case ProjectRole.MANAGER:
          return { color: "#FFF7EF", textColor: "#F99534" }
        case ProjectRole.COLLABORATOR:
          return { color: "#EAFBF5", textColor: "#52C41A" }
        case ProjectRole.RECORDER:
        case ProjectRole.RECORDER_SELF_ONLY:
          return { color: "#F0F5FF", textColor: "#2F54EB" }
        case ProjectRole.EXPLORER:
        case ProjectRole.EXPLORER_SELF_ONLY:
          return { color: "#EDF4FF", textColor: "#1A79FF" }
        case ProjectRole.VIEWER:
        case ProjectRole.VIEWER_SELF_ONLY:
          return { color: "#F6F6F6", textColor: "#666666" }
      }
    }

    return { color: "#F9953", textColor: "#F99534" }
  })

  const projectRoleOptions = computed(() => {
    const role = toValue(roleRef)

    return getProjectRoleInfo(role as ProjectRole, toValue(projectType) || ProjectType.PUBLIC)
  })

  const labRoleOptions = computed(() => {
    const role = toValue(roleRef)

    return getLabRoleInfo(role as LabRole)
  })

  return {
    color,
    roleLabel,
    projectRoleOptions,
    labRoleOptions,
  }
}

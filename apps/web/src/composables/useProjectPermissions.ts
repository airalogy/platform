import type { MaybeRef } from "@vueuse/core"
import { ProjectRole, ProjectType } from "@/enum"
import { computed, toValue } from "vue"

/**
 * Enum for project-level actions.
 */
export enum ProjectAction {
  SET_MANAGER,
  ASSIGN_ROLES,
  CREATE_PROTOCOL,
  MANAGE_OWN_PROTOCOLS,
  MANAGE_OTHERS_PROTOCOLS,
  PREVIEW_OTHERS_PROTOCOLS,
  OPEN_DATA_ENTRY_FOR_OTHERS,
  SUBMIT_DATA_TO_OTHERS,
  VIEW_OWN_RECORDS,
  VIEW_OTHERS_RECORDS,
  DELETE_OWN_RECORDS,
  DELETE_OTHERS_RECORDS,
}

export const PROJECT_OWNER_ONLY = [ProjectRole.OWNER]
export const PROJECT_OWNER_AND_MANAGER = [ProjectRole.OWNER, ProjectRole.MANAGER]
export const ALL_PROJECT_ROLES = Object.values(ProjectRole).filter(value => typeof value === "number") as ProjectRole[]

type PermissionMap = Record<ProjectType, Record<ProjectAction, ProjectRole[]>>

export const projectPermissions: PermissionMap = {
  [ProjectType.PRIVATE]: {
    [ProjectAction.SET_MANAGER]: PROJECT_OWNER_ONLY,
    [ProjectAction.ASSIGN_ROLES]: PROJECT_OWNER_AND_MANAGER,
    [ProjectAction.CREATE_PROTOCOL]: [ProjectRole.OWNER, ProjectRole.MANAGER, ProjectRole.COLLABORATOR, ProjectRole.RECORDER],
    [ProjectAction.MANAGE_OWN_PROTOCOLS]: [ProjectRole.OWNER, ProjectRole.MANAGER, ProjectRole.COLLABORATOR, ProjectRole.RECORDER],
    [ProjectAction.MANAGE_OTHERS_PROTOCOLS]: PROJECT_OWNER_AND_MANAGER,
    [ProjectAction.PREVIEW_OTHERS_PROTOCOLS]: [ProjectRole.OWNER, ProjectRole.MANAGER, ProjectRole.COLLABORATOR, ProjectRole.RECORDER],
    [ProjectAction.OPEN_DATA_ENTRY_FOR_OTHERS]: [ProjectRole.OWNER, ProjectRole.MANAGER, ProjectRole.COLLABORATOR, ProjectRole.RECORDER],
    [ProjectAction.SUBMIT_DATA_TO_OTHERS]: [ProjectRole.OWNER, ProjectRole.MANAGER, ProjectRole.COLLABORATOR, ProjectRole.RECORDER],
    [ProjectAction.VIEW_OWN_RECORDS]: [ProjectRole.OWNER, ProjectRole.MANAGER, ProjectRole.COLLABORATOR, ProjectRole.RECORDER],
    [ProjectAction.VIEW_OTHERS_RECORDS]: [ProjectRole.OWNER, ProjectRole.MANAGER, ProjectRole.COLLABORATOR],
    [ProjectAction.DELETE_OWN_RECORDS]: PROJECT_OWNER_AND_MANAGER,
    [ProjectAction.DELETE_OTHERS_RECORDS]: PROJECT_OWNER_AND_MANAGER,
  },
  [ProjectType.PUBLIC]: {
    [ProjectAction.SET_MANAGER]: PROJECT_OWNER_ONLY,
    [ProjectAction.ASSIGN_ROLES]: PROJECT_OWNER_AND_MANAGER,
    [ProjectAction.CREATE_PROTOCOL]: [ProjectRole.OWNER, ProjectRole.MANAGER, ProjectRole.COLLABORATOR],
    [ProjectAction.MANAGE_OWN_PROTOCOLS]: [ProjectRole.OWNER, ProjectRole.MANAGER, ProjectRole.COLLABORATOR],
    [ProjectAction.MANAGE_OTHERS_PROTOCOLS]: PROJECT_OWNER_AND_MANAGER,
    [ProjectAction.PREVIEW_OTHERS_PROTOCOLS]: ALL_PROJECT_ROLES,
    [ProjectAction.OPEN_DATA_ENTRY_FOR_OTHERS]: [ProjectRole.OWNER, ProjectRole.MANAGER, ProjectRole.COLLABORATOR, ProjectRole.RECORDER, ProjectRole.RECORDER_SELF_ONLY, ProjectRole.EXPLORER, ProjectRole.EXPLORER_SELF_ONLY],
    [ProjectAction.SUBMIT_DATA_TO_OTHERS]: [ProjectRole.OWNER, ProjectRole.MANAGER, ProjectRole.COLLABORATOR, ProjectRole.RECORDER, ProjectRole.RECORDER_SELF_ONLY],
    [ProjectAction.VIEW_OWN_RECORDS]: [ProjectRole.OWNER, ProjectRole.MANAGER, ProjectRole.COLLABORATOR, ProjectRole.RECORDER, ProjectRole.RECORDER_SELF_ONLY],
    [ProjectAction.VIEW_OTHERS_RECORDS]: ALL_PROJECT_ROLES.filter(role => ![ProjectRole.RECORDER_SELF_ONLY, ProjectRole.EXPLORER_SELF_ONLY, ProjectRole.VIEWER_SELF_ONLY].includes(role)),
    [ProjectAction.DELETE_OWN_RECORDS]: PROJECT_OWNER_AND_MANAGER,
    [ProjectAction.DELETE_OTHERS_RECORDS]: PROJECT_OWNER_AND_MANAGER,
  },
}
export function checkProjectActionPermission(role: ProjectRole, type: ProjectType, action: ProjectAction): boolean {
  const allowedRoles = projectPermissions[type][action]
  if (!allowedRoles || !allowedRoles.length) {
    return false
  }
  return allowedRoles.includes(role)
}

/**
 * A composable to manage project-level permissions.
 *
 * @param project A reactive reference to the project information.
 */
export function useProjectPermissions(project: MaybeRef<Api.Project.MyProjectInfo | null>) {
  const userRole = computed((): ProjectRole => toValue(project)?.user_role)
  const projectType = computed((): ProjectType => toValue(project)?.type || ProjectType.PRIVATE)

  /**
   * Checks if the current user has permission to perform a given action.
   * @param action The action to check.
   */
  function checkPermission(action: ProjectAction): boolean {
    const role = userRole.value
    if (!role)
      return false

    return checkProjectActionPermission(role, projectType.value, action)
  }

  const canSetManager = computed(() => checkPermission(ProjectAction.SET_MANAGER))
  const canAssignRoles = computed(() => checkPermission(ProjectAction.ASSIGN_ROLES))
  const canCreateProtocol = computed(() => checkPermission(ProjectAction.CREATE_PROTOCOL))
  const canManageOwnProtocols = computed(() => checkPermission(ProjectAction.MANAGE_OWN_PROTOCOLS))
  const canManageOthersProtocols = computed(() => checkPermission(ProjectAction.MANAGE_OTHERS_PROTOCOLS))
  const canPreviewOthersProtocols = computed(() => checkPermission(ProjectAction.PREVIEW_OTHERS_PROTOCOLS))
  const canOpenDataEntryForOthers = computed(() => checkPermission(ProjectAction.OPEN_DATA_ENTRY_FOR_OTHERS))
  const canSubmitDataToOthers = computed(() => checkPermission(ProjectAction.SUBMIT_DATA_TO_OTHERS))
  const canViewOwnRecords = computed(() => checkPermission(ProjectAction.VIEW_OWN_RECORDS))
  const canViewOthersRecords = computed(() => checkPermission(ProjectAction.VIEW_OTHERS_RECORDS))
  const canDeleteOwnRecords = computed(() => checkPermission(ProjectAction.DELETE_OWN_RECORDS))
  const canDeleteOthersRecords = computed(() => checkPermission(ProjectAction.DELETE_OTHERS_RECORDS))

  const isOwner = computed(() => userRole.value === ProjectRole.OWNER)
  const isManager = computed(() => userRole.value === ProjectRole.MANAGER)
  const canShowSettings = computed(() => PROJECT_OWNER_AND_MANAGER.includes(userRole.value))

  return {
    userRole,
    isOwner,
    isManager,
    canShowSettings,
    canSetManager,
    canAssignRoles,
    canCreateProtocol,
    canManageOwnProtocols,
    canManageOthersProtocols,
    canPreviewOthersProtocols,
    canOpenDataEntryForOthers,
    canSubmitDataToOthers,
    canViewOwnRecords,
    canViewOthersRecords,
    canDeleteOwnRecords,
    canDeleteOthersRecords,
  }
}

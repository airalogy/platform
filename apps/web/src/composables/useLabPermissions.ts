import type { MaybeRef } from "@vueuse/core"
import { LabRole } from "@/enum"
import { computed, toValue } from "vue"
import { useAuthStore } from "../store/modules/auth"

export enum LabAction {
  SET_MANAGER,
  SET_OWNER,
  ASSIGN_ROLES,
  MANAGE_GROUP,
  MANAGE_LAB,
  DELETE_LAB,
  MANAGE_OWN_PROJECTS,
  MANAGE_OTHERS_PROJECTS,
  VIEW_OWN_PROJECTS,
  VIEW_OTHERS_PRIVATE_PROJECTS,
  DELETE_OWN_PROJECTS,
  DELETE_OTHERS_PROJECTS,
}
export const LAB_OWNER_ONLY: LabRole[] = [LabRole.OWNER]
export const LAB_OWNER_AND_MANAGER: LabRole[] = [LabRole.OWNER, LabRole.MANAGER]
export const ALL_LAB_ROLES: LabRole[] = Object.values(LabRole).filter(value => typeof value === "number") as LabRole[]

export const labPermissions: Record<LabAction, LabRole[]> = {
  [LabAction.SET_MANAGER]: LAB_OWNER_ONLY,
  [LabAction.SET_OWNER]: LAB_OWNER_ONLY,
  [LabAction.ASSIGN_ROLES]: LAB_OWNER_AND_MANAGER,
  [LabAction.MANAGE_LAB]: LAB_OWNER_AND_MANAGER,
  [LabAction.DELETE_LAB]: LAB_OWNER_ONLY,
  [LabAction.MANAGE_GROUP]: LAB_OWNER_AND_MANAGER,
  [LabAction.MANAGE_OWN_PROJECTS]: ALL_LAB_ROLES,
  [LabAction.MANAGE_OTHERS_PROJECTS]: LAB_OWNER_AND_MANAGER,
  [LabAction.VIEW_OWN_PROJECTS]: ALL_LAB_ROLES,
  [LabAction.VIEW_OTHERS_PRIVATE_PROJECTS]: LAB_OWNER_AND_MANAGER,
  [LabAction.DELETE_OWN_PROJECTS]: ALL_LAB_ROLES,
  [LabAction.DELETE_OTHERS_PROJECTS]: LAB_OWNER_AND_MANAGER,
}
export function checkLabActionPermission(role: LabRole, action: LabAction): boolean {
  const allowedRoles = labPermissions[action]
  if (!allowedRoles || !allowedRoles.length) {
    return false
  }
  return allowedRoles.includes(role)
}

/**
 * A composable to manage lab-level permissions.
 *
 * @param lab A reactive reference to the lab information.
 */
export function useLabPermissions(lab: MaybeRef<Api.Lab.LabInfo | null>) {
  const authStore = useAuthStore()
  const userRole = computed(() => {
    const currUserId = authStore.userInfo.id
    const user = toValue(lab)?.users?.find(({ id }) => id === currUserId)
    if (!user) {
      return null
    }

    return user.lab_role
  })

  const isOwner = computed(() => userRole.value === LabRole.OWNER)
  const isManager = computed(() => userRole.value === LabRole.MANAGER)
  function checkPermission(action: LabAction): boolean {
    const role = userRole.value
    if (!role)
      return false

    return checkLabActionPermission(role, action)
  }

  const canAssignRoles = computed(() => checkPermission(LabAction.ASSIGN_ROLES))
  const canManageGroup = computed(() => checkPermission(LabAction.MANAGE_GROUP))
  const canManageLab = computed(() => checkPermission(LabAction.MANAGE_LAB))
  const canDeleteLab = computed(() => checkPermission(LabAction.DELETE_LAB))

  return {
    userRole,
    isOwner,
    isManager,
    canAssignRoles,
    canManageGroup,
    canManageLab,
    canDeleteLab,
  }
}

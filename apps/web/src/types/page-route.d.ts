import type { RouteRecordRaw } from "vue-router"

export type RootNameKey = "root"
export type AuthRouteNameKey = "auth" | "login" | "sign-up" | "forget-password" | "instance-setup" | "join-lab" | "password-reset"
export type UserProfileNameKey = "user-profile" | "user-profile" | "profile-settings" | "profile-groups" | "profile-questions" | "profile-answers" | "profile-starred" | "profile-protocols" | "profile-records"
export type HomeNameKey = "home"
export type ProjectsNameKey = "projects" | "project-dashboard" | "project-starred"
export type LabsNameKey = "labs" | "labs-my" | "labs-public"
export type LabInfoNameKey = "lab-projects" | "lab-records" | "lab-members" | "lab-groups" | "lab-organization" | "lab-teams" | "lab-access" | "lab-settings"
export type GroupsNameKey = "lab-group-projects" | "lab-group-members" | "lab-group-settings"
export type ProjectInfoNameKey = "project-protocols" | "project-records" | "project-members" | "project-settings"
export type ProtocolNameKey = "protocols" | "protocols-my"
export type ProtocolInfoNameKey = "protocol-info" | "protocol-discussion-detail" | "protocol-discussion-edit" | "protocol-records" | "protocol-detail" | "protocol-discussions" | "protocol-settings" | "protocol-record-report" | "protocol-info-apply-protocol"
export type ProtocolRecordNameKey = "add-protocol-record" | "add-protocol-record-from-workflow"
export type AuthorizeNameKey = "authorize"
export type ExceptionNameKey = "not-found" | "no-permission" | "server-error" | "path-not-found" | "403" | "404" | "500" | "lab-not-found" | "project-not-found" | "protocol-not-found"
export type HubNameKey = "hub" | "hub-list" | "hub-detail" | "hub-search" | "hub-publish" | "hub-detail-protocol" | "hub-detail-record" | "hub-detail-discussion"
export type AdminNameKey = "admin" | "admin-dashboard" | "admin-analytics" | "admin-users" | "admin-users-list" | "admin-user-roles" | "admin-permissions" | "admin-content" | "admin-system"
export type AdminMenuNameKey = "admin-overview" | "admin-analytics" | "admin-users-list" | "admin-user-roles" | "admin-permissions" | "admin-labs" | "admin-projects" | "admin-protocols" | "admin-settings" | "admin-logs" | "admin-monitoring"
export type SearchNameKey =
  | "search"
  | "search-index"
  | "search-protocol"
  | "search-record"
  | "search-discussion"
export type DemoNameKey = "organization-demo"

export type RouteNameKey = RootNameKey | HomeNameKey | AuthRouteNameKey | UserProfileNameKey | ProjectsNameKey | LabsNameKey | LabInfoNameKey | GroupsNameKey | ProjectInfoNameKey | ProtocolNameKey | ProtocolInfoNameKey | ProtocolRecordNameKey | AuthorizeNameKey | ExceptionNameKey | HubNameKey | SearchNameKey | DemoNameKey | "protocol-editor" | "protocol-editor-playground" | "excel-editor" | AdminNameKey | AdminMenuNameKey | "global-chat"

export type CustomRoute<T extends RouteNameKey = RouteNameKey> = RouteRecordRaw & {
  name?: T
  // path: string
  // redirect?: string
  // meta: {
  //   title: string
  //   i18nKey?: string
  //   icon?: string
  //   constant?: boolean
  //   order?: number
  // }
  children?: CustomRoute[]
}

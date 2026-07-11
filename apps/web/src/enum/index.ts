export enum SetupStoreId {
  APP = "app-store",
  THEME = "theme-store",
  AUTH = "auth-store",
  ROUTE = "route-store",
  TAB = "tab-store",
  MODAL = "modal-store",
  PACKAGE = "package-store",
  EDITOR = "editor-store",
  ALIAS = "alias-store",
  INSTANCE = "instance-store",
}

export enum LabRole {
  OWNER = 1,
  MANAGER = 2,
  MEMBER = 3,
}

export enum ProjectRole {
  OWNER = 1,
  MANAGER = 20,
  COLLABORATOR = 30,
  RECORDER = 40,
  RECORDER_SELF_ONLY = 45,
  EXPLORER = 50,
  EXPLORER_SELF_ONLY = 55,
  VIEWER = 60,
  VIEWER_SELF_ONLY = 65,
}

export enum GroupRole {
  MANAGER = 1,
  MEMBER = 2,
}

export enum ProjectType {
  PRIVATE = 1,
  PUBLIC = 2,
}

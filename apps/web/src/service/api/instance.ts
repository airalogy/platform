import { request } from "../request"

export type DeploymentMode = "community" | "single_lab"
export type SignupMode = "open" | "invite_only" | "disabled"
export type LabStructureMode = "flat" | "structured"

export interface InstanceLabInfo {
  id: string
  uid: string
  name: string
}

export interface InstanceStatus {
  deployment_mode: DeploymentMode
  single_lab: boolean
  initialized: boolean
  signup_mode: SignupMode
  bootstrap_token_required: boolean
  site_url: string
  lab_structure_mode: LabStructureMode
  lab: InstanceLabInfo | null
}

export interface BootstrapPayload {
  setupToken: string
  username: string
  email: string
  name: string
  password: string
  confirmPassword: string
}

export async function fetchInstanceStatus() {
  return request<InstanceStatus>({
    url: "/instance",
    metadata: { showError: false },
  })
}

export async function postInstanceBootstrap(payload: BootstrapPayload) {
  return request<{ token: string, user: Api.Auth.UserInfo, lab: InstanceLabInfo }>({
    url: "/instance/bootstrap",
    method: "POST",
    data: {
      username: payload.username,
      setup_token: payload.setupToken,
      email: payload.email,
      name: payload.name,
      password: payload.password,
      confirm_password: payload.confirmPassword,
    },
  })
}

export interface InvitationInfo {
  email: string
  expires_at: string
  lab: InstanceLabInfo
  existing_account: boolean
}

export async function fetchInvitation(token: string) {
  return request<InvitationInfo>({
    url: `/instance/invitations/${encodeURIComponent(token)}`,
    metadata: { showError: false },
  })
}

export async function postInvitation(payload: {
  email: string
  labRole: Api.Lab.LabRole
  projectRole: Api.Project.ProjectRole
}) {
  return request<{
    id: string
    email: string
    expires_at: string
    existing_account: boolean
    url: string
  }>({
    url: "/instance/invitations",
    method: "POST",
    data: {
      email: payload.email,
      lab_role: payload.labRole,
      project_role: payload.projectRole,
    },
  })
}

export async function acceptInvitation(token: string) {
  return request<{ success: boolean, lab: InstanceLabInfo }>({
    url: `/instance/invitations/${encodeURIComponent(token)}/accept`,
    method: "POST",
  })
}

export async function createPasswordResetLink(userId: string) {
  return request<{ id: string, email: string, expires_at: string, url: string }>({
    url: "/instance/password-reset-links",
    method: "POST",
    data: { user_id: userId },
  })
}

export async function fetchPasswordReset(token: string) {
  return request<{ email: string, expires_at: string }>({
    url: `/instance/password-resets/${encodeURIComponent(token)}`,
    metadata: { showError: false },
  })
}

export async function postPasswordReset(token: string, payload: {
  password: string
  confirmPassword: string
}) {
  return request<{ success: boolean }>({
    url: `/instance/password-resets/${encodeURIComponent(token)}`,
    method: "POST",
    data: {
      password: payload.password,
      confirm_password: payload.confirmPassword,
    },
  })
}

export async function putOwnPassword(payload: {
  currentPassword: string
  password: string
  confirmPassword: string
}) {
  return request<{ success: boolean, token: string }>({
    url: "/instance/account/password",
    method: "PUT",
    data: {
      current_password: payload.currentPassword,
      password: payload.password,
      confirm_password: payload.confirmPassword,
    },
  })
}

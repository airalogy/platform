declare namespace Api {
  namespace Lab {
    import type { LabRole as LabRoleEnum } from "@/enum"

    type LabRole = LabRoleEnum
    type GroupType = 1 | 2

    interface ProtocolItem {
      id: string
      package: any // Define proper type if needed
      history: any[] // Define proper type if needed
    }

    interface LabInfo {
      avatar?: string | null
      create_user_id: string
      created_at: string
      description: string
      uid: string
      id: string
      name: string
      labs_count: number
      projects_count: number
      custom_projects_count?: number
      default_projects_count?: number
      default_projects_protocols_count?: number
      type: GroupType
      updated_at: string
      users_count: number
      // user_role?: LabRole
      users: (Omit<Auth.UserInfo, "role"> & { lab_role: LabRole })[]
      logo?: string | null
      logo_url?: string | null
      public_access_role: LabRoleEnum
    }

    interface ForceDeletePreview {
      members: number
      groups: number
      projects_total: number
      projects_active: number
      projects_deleted: number
      projects_default: number
      protocols_total: number
      protocols_active: number
      records_total: number
      records_active: number
      files_total: number
    }

    type ForceDeleteJobStatus = "pending" | "running" | "succeeded" | "failed"

    interface ForceDeleteJob {
      id: number
      lab_id: string
      lab_uid_snapshot: string
      lab_name_snapshot: string
      requested_by_user_id: string
      status: ForceDeleteJobStatus
      impact_summary: ForceDeletePreview
      failure_reason?: string | null
      requested_at: string
      started_at?: string | null
      finished_at?: string | null
    }

    interface UsersLabInfo extends LabInfo {
      user_role: LabRole
    }
    interface LabItem {
      id: string
      uid: string
      name: string
      label: string
      role: LabRole
      avatar?: string
      protocols: { count: number, list: ProtocolItem[] }
      members: { count: number, list: Partial<{ name: string, avatar: string }>[] }
      projects: { count: number, list: Project.ProjectItem[] }
      protocols: { count: number, list: Protocol.ProtocolItem[] }
    }

    interface MemberListItem extends Api.Alias.AliasFields {
      avatar: string | null
      avatar_url?: string | null
      id: string
      email: string
      lab_role: LabRole
      updated_at: string
      username: string
      name: string
      user_alias: string | null
    }
  }
}

declare namespace Api {
  namespace Project {
    import type { LabRole, ProjectRole as ProjectRoleEnum, ProjectType } from "@/enum"

    type ProjectRole = ProjectRoleEnum

    interface MyProjectInfo {
      id: string
      name: string
      uid: string
      create_user_id: string
      created_at: string
      description: string
      lab_id: string
      lab_uid: string
      lab_name: string
      parent_project_id?: string | null
      parent_project_uid?: string | null
      parent_project_name?: string | null
      group_name?: string
      updated_at: string
      display_name?: string
      type: ProjectType
      logo?: string | null
      logo_url?: string | null
      protocols_count: number
      users_count: number
      children_count?: number
      has_children?: boolean
      depth?: number
      user_role: ProjectRole
      user_lab_role: LabRole
      project_id: string
      project_uid: string
      public_access_role: ProjectRole
    }

    interface ProjectItem {
      id: string
      uid: string
      name: string
      label: string
      owner: Pick<Auth.UserInfo, "id" | "username">
      createdAt: string
      members: { count: number, list: Partial<{ name: string, avatar: string }>[] }
      stars: number
      protocols: { count: number, list: Protocol.ProtocolItem[] }
      groupName: string
      avatar?: string
      role?: "owner" | "member" | "recorder" | "viewer" | "default"
    }

    interface MemberListItem extends Api.Alias.AliasFields {
      avatar: string | null
      avatar_url?: string | null
      email: string
      id: string
      project_role: ProjectRole
      updated_at: Date
      username: string
      name: string
      group_id?: string
      group_name?: string
      group_uid?: string
    }
  }
}

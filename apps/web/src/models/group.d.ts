declare namespace Api {
  namespace Groups {
    import type { ProjectRole } from "../enum"

    type GroupsRole = Api.Project.ProjectRole
    type GroupType = 1 | 2

    interface GroupsInfo {
      avatar?: string | null
      create_user_id: string
      created_at: string
      description: string
      uid: string
      id: string
      name: string
      labs_count: number
      projects_count: number
      type: GroupType
      updated_at: string
      users_count: number
      user_role: GroupsRole
      users: Auth.UserInfo[]
      projects: Project.MyProjectInfo[]
    }

    interface MyGroupsInfo extends GroupsInfo {
      lab_id: string
      lab_uid: string
      lab_name: string
      user_role: GroupsRole
    }

    interface MemberItem {
      user_id: string
      role: GroupsRole
    }

    interface SearchMemberItem extends Auth.UserInfo { }

    interface MemberListItem extends Api.Alias.AliasFields {
      avatar_url: string | null
      id: string
      email: string
      lab_role: GroupsRole
      updated_at: string
      username: string
      name: string
      group_role?: ProjectRole
    }

    interface GroupProjectItem {
      create_user_id: string
      created_at: string
      description: string
      group_role: GroupsRole
      id: string
      lab_id: string
      name: string
      status: 1 | 2
      type: 1 | 2
      uid: string
      updated_at: string
    }
  }
}

declare namespace Api {
  namespace Activity {
    interface BaseActivityInfo {
      id: string
      uid: string
      name: string
    }

    interface ActivityItem {
      id: string
      uid?: string
      name?: string
      user: Api.Auth.UserInfo
      description: string
      action: "created" | "joined"
      project: BaseActivityInfo
      lab: BaseActivityInfo
      created_at: string
      node?: BaseActivityInfo
      record?: Partial<RecordInfo>
      protocol?: BaseActivityInfo
      group?: BaseActivityInfo
    }
  }
}

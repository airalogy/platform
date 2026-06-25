declare namespace Api {
  namespace Member {
    interface MemberItem {
      name: string
      id: string
      value: string
      email: string
      avatar?: string
      role: "owner" | "member" | "recorder" | "viewer" | "default"
    }
  }
}

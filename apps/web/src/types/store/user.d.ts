export interface IUserInfo {
  name: string | null
  id: number | null
  role: string | null
  roles: string[] | null
  avatar: string | null
}

export interface ILoginInfo {
  user: IUserInfo
  auth_token: string
}

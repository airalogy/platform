export interface Alias {
  id: string
  alias: string
  priority: number
}

export interface UserAliases {
  [userId: string]: Alias[]
}

export interface AliasState {
  aliases: UserAliases
}

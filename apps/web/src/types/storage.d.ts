import type { IRecordData } from "@/views/project-protocols/types"

/** The storage namespace */
export namespace AppStorage {
  interface Session {
    /** The theme color */
    themeColor: string
    // /**
    //  * the theme settings
    //  */
    // themeSettings: Theme.ThemeSetting;
  }

  interface Local {
    /** The i18n language */
    "lang": I18n.LangType
    /** The token */
    "token": string
    /** The refresh token */
    "refreshToken": string
    /** The user info */
    "userInfo": Api.Auth.UserInfo
    /** The theme color */
    "themeColor": string
    /** The theme settings */
    "themeSettings": Theme.ThemeSetting
    /**
     * The override theme flags
     *
     * The value is the build time of the project
     */
    "overrideThemeFlag": string
    /** The global tabs */
    "globalTabs": App.Global.Tab[]
    "chatStorage": Chat.ChatState
    "promptStore": Chat.PromptState
    "protocol": Protocol.ResearchNodeData
    "pinyinDict": Record<string, string>
    "unitRecordDraft": Record<string, Record<string, { data: IRecordData, timestamp: number }>>
    "protocol-workflow": {
      flowNodesRecord: any
      modelRecord: any
      record: any
      workflowNodesRecord: any
    }
  }
}

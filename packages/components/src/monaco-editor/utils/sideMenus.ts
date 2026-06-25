import type { Component } from "vue"
import AiralogyIcon from "~icons/local/ai-menu-icon"
import ProtocolIcon from "~icons/local/protocol-menu-icon"
import FilesIcon from "~icons/tabler/files"
import SearchIcon from "~icons/tabler/search"
import SettingsIcon from "~icons/tabler/settings"

import ChatPanel from "../modules/panel/chat.vue"
import FileExplorer from "../modules/panel/file-explorer.vue"
import ProtocolDocumentsPanel from "../modules/panel/protocol-documents.vue"
import SettingsPanel from "../modules/panel/settings-panel.vue"

export interface ISideMenuItem {
  icon: Component
  key: string
  label: string
  component: Component | null
  componentProps?: Record<string, any>
  componentEvents?: Record<string, any>
  panelSize?: Record<"minSplitSize" | "collapseThreshold", number>
}

export const fileSideMenu: ISideMenuItem = {
  icon: FilesIcon,
  key: "file",
  label: "file",
  component: FileExplorer,
}

export const chatSideMenu: ISideMenuItem = {
  icon: AiralogyIcon,
  key: "airalogy",
  label: "airalogy",
  component: ChatPanel,
  panelSize: {
    minSplitSize: 500,
    collapseThreshold: 120,
  },
}
export const documentSideMenu: ISideMenuItem = {
  icon: ProtocolIcon,
  key: "protocol-documents",
  label: "Protocol Documents",
  component: ProtocolDocumentsPanel,
  panelSize: {
    minSplitSize: 500,
    collapseThreshold: 120,
  },
}

export const searchSideMenu: ISideMenuItem = {
  icon: SearchIcon,
  key: "search",
  label: "search",
  component: null,
}
export const settingSideMenu: ISideMenuItem = {
  icon: SettingsIcon,
  key: "settings",
  label: "settings",
  component: SettingsPanel,
  componentProps: {
    protocolInfo: null,
  },
  panelSize: {
    minSplitSize: 600,
    collapseThreshold: 220,
  },
}

export const defaultSideMenus: ISideMenuItem[] = [
  fileSideMenu,
  chatSideMenu,
  documentSideMenu,
  searchSideMenu,
  settingSideMenu,
]

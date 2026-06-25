import enUS from "./langs/en-us.json"
import zhCN from "./langs/zh-cn.json"

const locales: Record<I18n.LangType, I18n.Schema> = {
  "zh-CN": zhCN,
  "en-US": enUS,
}

export default locales

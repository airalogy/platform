import { snakeCase } from "@/utils/changeCase"
import { DISPLAY_NAME_TRIM } from "../constants/reg"
import { getPinyin } from "./zhCharToPinyin"

export async function convertDisplayname(displayName?: string) {
  if (!displayName) {
    return ""
  }

  const trimmed = displayName.trim()
  const pinyin = await getPinyin(trimmed)
  const name = pinyin
    .replaceAll(/\W/g, "_")
    .replace(DISPLAY_NAME_TRIM, "")
    .replace(/[_-]{2,}/g, "_")

  return snakeCase(name)
}

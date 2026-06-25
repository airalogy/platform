import { DISPLAY_NAME_TRIM } from "../constants/reg"
import { localStg } from "./storage"

let localDict: Record<string, string> | null = null
/**
 * 解析各种字典文件，所需的字典文件必须在本JS之前导入
 */
export async function parseDict() {
  const dict = localStg.get("pinyinDict")
  if (dict) {
    localDict = dict
    return dict
  }
  const rawDict: Record<string, string> = (await import("@/utils/pinyin_dict")).default
  const record: Record<string, string> = {}

  for (const i in rawDict) {
    const temp = rawDict[i]
    for (let j = 0, len = temp.length; j < len; j++) {
      const char = temp[j]
      if (!record[char])
        record[char] = i // 不考虑多音字
    }
  }

  localStg.set("pinyinDict", record)
  localDict = record
  return record
}

/**
 * 根据汉字获取拼音，如果不是汉字直接返回原字符
 * @param input 要转换的汉字
 * @param splitter 分隔字符，默认用空格分隔
 * @param withtone 返回结果是否包含声调，默认是
 * @param polyphone 是否支持多音字，默认否
 */
export async function getPinyin(input: string, splitter = "_") {
  if (!input || !input.trim())
    return ""
  const result: string[] = []

  const dict = localDict || (await parseDict())
  if (!dict) {
    return ""
  }

  let notChinese = ""

  for (let i = 0, len = input.length; i < len; i++) {
    const char = input.charAt(i)
    const pinyin = dict[char]
    if (pinyin) {
      // 插入拼音
      // 空格，把notChinese作为一个词插入
      if (notChinese) {
        const trimmed = notChinese.replace(DISPLAY_NAME_TRIM, "")
        if (trimmed) {
          result.push(trimmed)
        }
        notChinese = ""
      }
      result.push(pinyin)
    }
    else if (!char.trim()) {
      // 空格，插入之前的非中文字符
      const trimmed = notChinese.replace(DISPLAY_NAME_TRIM, "")
      if (trimmed) {
        result.push(trimmed)
      }

      notChinese = ""
    }
    else {
      notChinese += char
    }
  }
  if (notChinese) {
    const trimmed = notChinese.replace(DISPLAY_NAME_TRIM, "")
    if (trimmed) {
      result.push(trimmed)
    }
  }

  return result.join(splitter)
}

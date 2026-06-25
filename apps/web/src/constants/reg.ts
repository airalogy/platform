/**
 * Local regex constants for apps/web
 * Note: AIMD-related regexes should be imported from @airalogy/shared/constants
 */

export const REG_DISPLAY_NAME = /^[\u4E00-\u9FA5\w\-]{4,16}$/
export const REG_USER_NAME = /^[a-z0-9][\w\-]{4,14}[a-z0-9]$/i

/** Phone reg */
export const REG_PHONE
  = /^1((3\d)|(4[014-9])|(5[0-35-9])|(6[2567])|(7[0-8])|(8\d)|(9[0-35-9]))\d{8}$/

/**
 * Password reg
 *
 * 6-18 characters, including letters, numbers, and underscores
 */
export const REG_PWD = /^\w{6,18}$/

/** Email reg */
export const REG_EMAIL
  = /^(([^<>()[\]\\.,;:\s@"]+(\.[^<>()[\]\\.,;:\s@"]+)*)|(".+"))@((\[\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\])|(([a-z\-0-9]+\.)+[a-z]{2,}))$/i

/** Six digit code reg */
export const REG_CODE_SIX = /^\d{6}$/

/** Four digit code reg */
export const REG_CODE_FOUR = /^\d{4}$/

/** Url reg */
export const REG_URL
  // eslint-disable-next-line regexp/no-useless-quantifier, regexp/no-super-linear-backtracking
  = /(((^https?:(?:\/\/)?)(?:[-;:&=+$,\w]+@)?[A-Za-z0-9.-]+(?::\d+)?|(?:www.|[-;:&=+$,\w]+@)[A-Za-z0-9.-]+)((?:\/[+~%/.\w-]*)?\??[-+=&;%@.\w]*(?:#\w*)?)?)$/

export const DISPLAY_NAME_TRIM = /(^[_-]+)|([_-]+$)/g

export const AIRALOGY_FILE_ID_REG = /airalogy\.id\.file\.([\w-]+)\.([^.]+)$/

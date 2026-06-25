import type { AnyColor, HslColor, HsvColor, RgbColor } from "colord"
import { colord, extend } from "colord"
import labPlugin from "colord/plugins/lab"
import mixPlugin from "colord/plugins/mix"
import namesPlugin from "colord/plugins/names"

extend([namesPlugin, mixPlugin, labPlugin])

export function isValidColor(color: AnyColor) {
  return colord(color).isValid()
}

export function getHex(color: AnyColor) {
  return colord(color).toHex()
}

export function getRgb(color: AnyColor) {
  return colord(color).toRgb()
}

export function getHsl(color: AnyColor) {
  return colord(color).toHsl()
}

export function getHsv(color: AnyColor) {
  return colord(color).toHsv()
}

export function getDeltaE(color1: AnyColor, color2: AnyColor) {
  return colord(color1).delta(color2)
}

export function transformHslToHex(color: HslColor) {
  return colord(color).toHex()
}

/**
 * Add color alpha
 *
 * @param color - Color
 * @param alpha - Alpha (0 - 1)
 */
export function addColorAlpha(color: AnyColor, alpha: number) {
  return colord(color).alpha(alpha).toHex()
}

/**
 * Mix color
 *
 * @param firstColor - First color
 * @param secondColor - Second color
 * @param ratio - The ratio of the second color (0 - 1)
 */
export function mixColor(firstColor: AnyColor, secondColor: AnyColor, ratio: number) {
  return colord(firstColor).mix(secondColor, ratio).toHex()
}

/**
 * Transform color with opacity to similar color without opacity
 *
 * @param color - Color
 * @param alpha - Alpha (0 - 1)
 * @param bgColor Background color (usually white or black)
 */
export function transformColorWithOpacity(color: AnyColor, alpha: number, bgColor = "#ffffff") {
  const originColor = addColorAlpha(color, alpha)
  const { r: oR, g: oG, b: oB } = colord(originColor).toRgb()

  const { r: bgR, g: bgG, b: bgB } = colord(bgColor).toRgb()

  function calRgb(or: number, bg: number, al: number) {
    return bg + (or - bg) * al
  }

  const resultRgb: RgbColor = {
    r: calRgb(oR, bgR, alpha),
    g: calRgb(oG, bgG, alpha),
    b: calRgb(oB, bgB, alpha),
  }

  return colord(resultRgb).toHex()
}

/**
 * Is white color
 *
 * @param color - Color
 */
export function isWhiteColor(color: AnyColor) {
  return colord(color).isEqual("#ffffff")
}
/** Hue step */
export const hueStep = 2
/** Saturation step, light color part */
export const saturationStep = 16
/** Saturation step, dark color part */
export const saturationStep2 = 5
/** Brightness step, light color part */
export const brightnessStep1 = 5
/** Brightness step, dark color part */
export const brightnessStep2 = 15
/** Light color count, main color up */
export const lightColorCount = 5
/** Dark color count, main color down */
export const darkColorCount = 4

/**
 * Get hue
 *
 * @param hsv - Hsv format color
 * @param i - The relative distance from 6
 * @param isLight - Is light color
 */
export function getHue(hsv: HsvColor, i: number, isLight: boolean) {
  let hue: number

  const hsvH = Math.round(hsv.h)

  if (hsvH >= 60 && hsvH <= 240) {
    hue = isLight ? hsvH - hueStep * i : hsvH + hueStep * i
  }
  else {
    hue = isLight ? hsvH + hueStep * i : hsvH - hueStep * i
  }

  if (hue < 0) {
    hue += 360
  }

  if (hue >= 360) {
    hue -= 360
  }

  return hue
}

/**
 * Get saturation
 *
 * @param hsv - Hsv format color
 * @param i - The relative distance from 6
 * @param isLight - Is light color
 */
export function getSaturation(hsv: HsvColor, i: number, isLight: boolean) {
  if (hsv.h === 0 && hsv.s === 0) {
    return hsv.s
  }

  let saturation: number

  if (isLight) {
    saturation = hsv.s - saturationStep * i
  }
  else if (i === darkColorCount) {
    saturation = hsv.s + saturationStep
  }
  else {
    saturation = hsv.s + saturationStep2 * i
  }

  if (saturation > 100) {
    saturation = 100
  }

  if (isLight && i === lightColorCount && saturation > 10) {
    saturation = 10
  }

  if (saturation < 6) {
    saturation = 6
  }

  return saturation
}

/**
 * Get value of hsv
 *
 * @param hsv - Hsv format color
 * @param i - The relative distance from 6
 * @param isLight - Is light color
 */
export function getValue(hsv: HsvColor, i: number, isLight: boolean) {
  let value: number

  if (isLight) {
    value = hsv.v + brightnessStep1 * i
  }
  else {
    value = hsv.v - brightnessStep2 * i
  }

  if (value > 100) {
    value = 100
  }

  return value
}
export { colord }

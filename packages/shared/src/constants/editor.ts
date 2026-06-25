import { ImageDisplay } from "@airalogy/shared/enum/editor"

export const DEFAULT_IMAGE_WIDTH = 200
export const DEFAULT_IMAGE_DISPLAY = ImageDisplay.INLINE
export const DEFAULT_IMAGE_URL_REGEX
  = /(https?:\/\/(?:www\.|(?!www))[a-zA-Z0-9][a-zA-Z0-9-]+[a-zA-Z0-9]\.\S{2,}|www\.[a-zA-Z0-9][a-zA-Z0-9-]+[a-zA-Z0-9]\.\S{2,}|https?:\/\/(?:www\.|(?!www))[a-zA-Z0-9]+\.\S{2,}|www\.[a-zA-Z0-9]+\.\S{2,})/

export const LINE_HEIGHT_100 = 1.7
export const DEFAULT_LINE_HEIGHT = "100%"

export const ALLOWED_NODE_TYPES = ["paragraph", "heading", "list_item", "todo_item"]

// eslint-disable-next-line regexp/no-super-linear-backtracking
export const NUMBER_VALUE_PATTERN = /^\d+(.\d+)?$/

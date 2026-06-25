import type { ExtensionRenderParams } from "../../index"
import type { CustomImageOptions, DownloadImageCommandProps } from "./types"
import { type FileInput, filterFiles, randomId } from "@airalogy/shared/utils"
import { NodeSelection } from "@tiptap/pm/state"
import { ReplaceStep } from "@tiptap/pm/transform"
import { mergeAttributes, VueNodeViewRenderer } from "@tiptap/vue-3"
import { AiralogyFile } from ".."
import InsertImageItem from "../../../modules/file/insert-image-item.vue"
import { parseAiralogyFileUrl } from "../utils"
import ImageViewBlock from "./modules/image-view-block.vue"
import { defaultCopyId, defaultCopyImage, defaultCopyLink, defaultDownloadImage } from "./utils/image-actions"

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    setImages: {
      setImages: (attrs: FileInput[]) => ReturnType
    }
    downloadImage: {
      downloadImage: (attrs: DownloadImageCommandProps) => ReturnType
    }
    copyImage: {
      copyImage: (attrs: DownloadImageCommandProps) => ReturnType
    }
    copyLink: {
      copyLink: (attrs: DownloadImageCommandProps) => ReturnType
    }
    // uploadImage: {
    //   uploadImage: (file: File) => ReturnType
    // }
    toggleImage: {
      toggleImage: () => ReturnType
    }
  }
}

export const Image = AiralogyFile.extend<CustomImageOptions>({
  name: "airalogyImage",
  atom: true,

  addOptions() {
    return {
      ...this.parent?.(),
      allowBase64: true,
      allowedMimeTypes: [],
      maxFileSize: 0,
      renderer({ editor, disabled, eventHandlers = {} }: ExtensionRenderParams) {
        return {
          component: InsertImageItem,
          componentProps: {
            editor,
            disabled,
            ...eventHandlers,
          },
        }
      },
    }
  },

  addAttributes() {
    return {
      ...this.parent?.(),
      id: {
        default: undefined,
      },
      width: {
        default: undefined,
      },
      height: {
        default: undefined,
      },
      fileName: {
        default: undefined,
      },
      fileType: {
        default: undefined,
      },
    }
  },

  addCommands() {
    return {
      setImages: (attrs: FileInput[]) =>
        ({ commands, state, chain }) => {
          const { onValidationError, allowedMimeTypes, maxFileSize, allowBase64 } = this.options
          const [validImages, errors] = filterFiles(attrs, {
            allowedMimeTypes,
            maxFileSize,
            allowBase64,
          })

          if (errors.length > 0 && onValidationError) {
            onValidationError(errors)
          }

          if (validImages.length > 0) {
            const { selection } = state
            const { from, to } = selection

            // Check if a complete node (e.g. image) is selected
            const isNodeSelection = selection instanceof NodeSelection && from !== to

            const imageNodes = validImages.map((image: any) => ({
              type: this.type.name,
              attrs: {
                id: randomId(),
                src: image.src instanceof File ? URL.createObjectURL(image.src) : image.src,
                alt: image.alt,
                title: image.title,
                airalogyId: image.id,
                fileName: image.src instanceof File ? image.src.name : null,
                fileType: image.src instanceof File ? image.src.type : null,
              },
            }))

            // If a node is selected, insert after it instead of replacing it
            if (isNodeSelection) {
              return commands.insertContentAt(to, imageNodes)
            }

            // Otherwise insert normally
            return commands.insertContent(imageNodes)
          }

          return false
        },
      downloadImage: (attrs: DownloadImageCommandProps) => () => {
        const downloadFunc = this.options.downloadImage || defaultDownloadImage
        void downloadFunc({ ...attrs, action: "download" }, this.options)
        return true
      },
      copyImage: (attrs: DownloadImageCommandProps) => () => {
        const copyImageFunc = this.options.copyImage || defaultCopyImage
        void copyImageFunc({ ...attrs, action: "copyImage" }, this.options)
        return true
      },
      copyLink: (attrs: DownloadImageCommandProps) => () => {
        const copyLinkFunc = this.options.copyLink || defaultCopyLink
        void copyLinkFunc({ ...attrs, action: "copyLink" }, this.options)
        return true
      },
      copyId: (attrs: DownloadImageCommandProps) => () => {
        const copyIdFunc = this.options.copyId || defaultCopyId
        void copyIdFunc({ ...attrs, action: "copyId" }, this.options)
        return true
      },
      // uploadImage: (file: File) => () => {
      //   const uploadFunc = this.options.uploadFn || defaultUploadImage
      //   void uploadFunc(file, this.editor as any, this.type, this.options)
      //   return true
      // },

      toggleImage: () =>
        ({ editor }) => {
          const input = document.createElement("input")
          input.type = "file"
          input.accept = this.options.allowedMimeTypes.join(",")
          input.onchange = () => {
            const files = input.files
            if (!files)
              return

            const { onValidationError, allowedMimeTypes, maxFileSize, allowBase64, onToggle } = this.options

            const [validImages, errors] = filterFiles(Array.from(files), {
              allowedMimeTypes,
              maxFileSize,
              allowBase64,
            })

            if (errors.length > 0 && onValidationError) {
              onValidationError(errors)
              return false
            }

            if (validImages.length === 0)
              return false

            if (onToggle) {
              onToggle(editor as any, validImages, editor.state.selection.from)
            }

            return false
          }

          input.click()
          return true
        },
    }
  },

  parseHTML() {
    return [
      {
        tag: "img[data-airalogy-id]",
        getAttrs: (node: HTMLElement) => {
          const airalogyId = node.getAttribute("data-airalogy-id")
          const extension = node.getAttribute("data-airalogy-extension")
          const alt = node.getAttribute("alt")
          const title = node.getAttribute("title")
          const src = node.getAttribute("src")

          return {
            alt,
            title,
            airalogyId,
            extension,
            src,
          }
        },
      },
      {
        tag: this.options.allowBase64
          ? "img[src]"
          : "img[src]:not([src^=\"data:\"])",
        getAttrs: (node: HTMLElement) => {
          const src = node.getAttribute("src")
          if (!src)
            return null

          const parsed = parseAiralogyFileUrl(src)
          if (parsed) {
            return {
              alt: node.getAttribute("alt"),
              title: node.getAttribute("title"),
              airalogyId: parsed.airalogyId,
              extension: parsed.extension,
              src,
            }
          }

          if (!this.options.allowBase64 && src.startsWith("data:")) {
            return null
          }

          return {
            src,
            alt: node.getAttribute("alt"),
            title: node.getAttribute("title"),
          }
        },
      },
    ]
  },

  renderHTML({ HTMLAttributes }) {
    const attrs = { ...this.options.HTMLAttributes, ...HTMLAttributes }
    if (attrs["data-airalogy-id"]) {
      delete attrs.src
    }
    return ["img", mergeAttributes(attrs)]
  },

  onTransaction({ transaction }) {
    transaction.steps.forEach((step) => {
      if (step instanceof ReplaceStep && step.slice.size === 0) {
        const deletedPages = transaction.before.content.cut(step.from, step.to)

        deletedPages.forEach((node) => {
          if (node.type.name === "airalogyImage") {
            const attrs = node.attrs

            if (attrs.src.startsWith("blob:")) {
              URL.revokeObjectURL(attrs.src)
            }

            this.options.onImageRemoved?.(attrs)
          }
        })
      }
    })
  },

  addNodeView() {
    return VueNodeViewRenderer(ImageViewBlock)
  },
})

export default Image

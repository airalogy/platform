import type { CommandProps, Editor } from "@tiptap/core"
import type { CustomFileOptions } from "./types"
import { getFileExtensionFromBasename } from "@airalogy/shared"
import { getAiralogyFileId } from "@airalogy/shared/utils/parseAiralogyId"
import { mergeAttributes, Node, nodeInputRule, nodePasteRule } from "@tiptap/core"
import { defaultUploadFn, getMatchAttributes, inputFinder, parseAiralogyFileUrl, pasteFinder } from "./utils"

/**
 * This extension allows you to insert images.
 * @see https://www.tiptap.dev/api/nodes/image
 */
export const AiralogyFile = Node.create<CustomFileOptions>({
  name: "airalogyFile",

  addOptions() {
    return {
      inline: false,
      allowBase64: true,
      allowedMimeTypes: [],
      HTMLAttributes: {},
      onUploadError: undefined,
      onUploadSuccess: undefined,
      protocolId: undefined,
      postAddAttachments: () => Promise.resolve({ data: { url: "", filename: "", id: "" } }),
      uploadFn: defaultUploadFn,
    }
  },

  inline() {
    return this.options.inline
  },

  group() {
    return this.options.inline ? "inline" : "block"
  },

  draggable: true,

  addAttributes() {
    return {
      src: {
        default: null,
      },
      alt: {
        default: null,
      },
      title: {
        default: null,
      },
      airalogyId: {
        default: null,
        renderHTML: (attributes) => {
          if (!attributes.airalogyId) {
            return {}
          }
          return {
            "data-airalogy-id": attributes.airalogyId,
          }
        },
      },
      extension: {
        default: null,
        renderHTML: (attributes) => {
          if (!attributes.extension) {
            return {}
          }
          return {
            "data-airalogy-extension": attributes.extension,
          }
        },
      },
      filename: {
        default: null,
        renderHTML: (attributes) => {
          if (!attributes.filename) {
            return {}
          }
        },
      },
    }
  },

  parseHTML() {
    return [
      {
        tag: "div[data-airalogy-id]",
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
          ? "div[data-src]"
          : "div[data-src]:not([data-src^=\"data:\"])",
        getAttrs: (node: HTMLElement) => {
          const src = node.getAttribute("data-src")
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
    return ["div", mergeAttributes(attrs)]
  },

  addInputRules() {
    return [
      nodeInputRule({
        find: inputFinder,
        type: this.type,
        getAttributes: getMatchAttributes,
      }),
    ]
  },

  addPasteRules() {
    return [
      nodePasteRule({
        find: pasteFinder,
        type: this.type,
        getAttributes: getMatchAttributes,
      }),
    ]
  },

  addCommands() {
    return {
      setFile: options => ({ commands }: CommandProps) => {
        return commands.insertContent({
          type: this.name,
          attrs: options,
        })
      },
      uploadFn: (file: File, protocolId?: string) => ({ tr, dispatch, editor }: CommandProps & { editor: Editor }) => {
        if (!dispatch)
          return false

        // Insert placeholder
        const placeholderText = `![Uploading ${file.name}...]()`
        const placeholderNode = this.type.schema.text(placeholderText)
        tr.replaceSelectionWith(placeholderNode)

        // Start upload
        this.options.postAddAttachments?.(file, protocolId || this.options.protocolId)
          .then((response) => {
            if (!response.data)
              return

            // Find placeholder position
            const { doc } = editor.state
            let startPos = -1
            let endPos = -1

            doc.nodesBetween(0, doc.content.size, (node: any, pos: number) => {
              if (node.isText && node.text?.includes(`![Uploading ${file.name}...]`)) {
                startPos = pos
                endPos = pos + node.nodeSize
                return false
              }
            })

            if (startPos !== -1 && endPos !== -1) {
              // Create new transaction since the original one might be outdated
              const newTr = editor.state.tr
              const imageNode = this.type.create({
                src: response.data.url,
                alt: response.data.filename,
                airalogyId: response.data.id,
              })
              newTr.replaceWith(startPos, endPos, imageNode)
              editor.view.dispatch(newTr)
            }

            this.options.onUploadSuccess?.(response.data)
          })
          .catch((error) => {
            this.options.onUploadError?.(error instanceof Error ? error : new Error(String(error)))
          })

        return true
      },
    }
  },

  addStorage() {
    return {
      markdown: {
        serialize(state: any, node: any) {
          const { airalogyId, extension, alt, title, src, filename } = node.attrs

          let out = ""
          if (airalogyId) {
            if (airalogyId.startsWith("airalogy.id.file.")) {
              out += `![${alt || ""}](${airalogyId}${title || ""})`
            }
            else {
              const fileExtension = extension || getFileExtensionFromBasename(filename || alt)
              out += `![${alt || ""}](${getAiralogyFileId(airalogyId, fileExtension)}${title || ""})`
            }
          }
          else if (src) {
            // Fallback for regular images
            out += `![${alt || ""}](${src || ""}${title || ""})`
          }

          if (state.out) {
            state.out += `\n\n${out}\n\n`
          }
          else {
            state.out += out
          }
        },
      },
    }
  },
})

export default AiralogyFile

import { AIRALOGY_FILE_ID_REG } from "@airalogy/shared/constants/reg"
import { Markdown } from "tiptap-markdown"

const BAD_PROTO_RE = /^vbscript|javascript|file|data:/
const GOOD_DATA_RE = /^data:image\/\S+;/

function validateLink(url: string) {
  // url should be normalized at this point, and existing entities are decoded
  const str = url.trim().toLowerCase()

  return BAD_PROTO_RE.test(str) ? GOOD_DATA_RE.test(str) || AIRALOGY_FILE_ID_REG.test(str) : true
}

export const TiptapMarkdown = Markdown.extend({
  name: "tiptapMarkdown",
  onCreate() {
    const { parser } = this.editor.storage.markdown
    const md = parser.md
    if (md) {
      md.validateLink = validateLink
    }
  },
})

export default TiptapMarkdown

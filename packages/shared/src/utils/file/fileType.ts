import type { FunctionalComponent, SVGAttributes } from "vue"
import { getFileExtensionFromBasename, getUriPathBasename } from "../uri"

// Icon imports from file-icons.ts
import IconFileCode from "~icons/ion/code-slash-outline"
import IconFileDocument from "~icons/ion/document-outline"
import IconFileImage from "~icons/ion/image-outline"
import IconFileJson from "~icons/ion/logo-javascript"
import IconFileMarkdown from "~icons/ion/logo-markdown"
import IconFileText from "~icons/ion/text-outline"
import AIMDIcon from "~icons/shared/logo-icon"
// Tabler file type icons (monochrome, consistent style)
import CSVIcon from "~icons/tabler/file-type-csv"
import DocIcon from "~icons/tabler/file-type-doc"
import IconFilePdf from "~icons/tabler/file-type-pdf"
import PptIcon from "~icons/tabler/file-type-ppt"
import XlsIcon from "~icons/tabler/file-type-xls"
import ZipIcon from "~icons/tabler/file-type-zip"
// VSCode icons for code files (optional: can be replaced with tabler if needed)
import CSSIcon from "~icons/vscode-icons/file-type-css"
import ESLintIcon from "~icons/vscode-icons/file-type-eslint"
import GitIcon from "~icons/vscode-icons/file-type-git"
import HTMLIcon from "~icons/vscode-icons/file-type-html"
import ImageIcon from "~icons/vscode-icons/file-type-image"
import JSIcon from "~icons/vscode-icons/file-type-js"
import MJSIcon from "~icons/vscode-icons/file-type-js-official"
import JSONIcon from "~icons/vscode-icons/file-type-json"
import MarkdownIcon from "~icons/vscode-icons/file-type-markdown"
import PrettierIcon from "~icons/vscode-icons/file-type-prettier"
import PythonIcon from "~icons/vscode-icons/file-type-python"
import TSXIcon from "~icons/vscode-icons/file-type-reactjs"
import TextIcon from "~icons/vscode-icons/file-type-text"
import TSIcon from "~icons/vscode-icons/file-type-typescript"
import VueIcon from "~icons/vscode-icons/file-type-vue"
import YAMLIcon from "~icons/vscode-icons/file-type-yaml"

export const standardFileTypes: Record<string, string[]> = Object.freeze({
  "application/andrew-inset": ["ez"],
  "application/appinstaller": ["appinstaller"],
  "application/applixware": ["aw"],
  "application/appx": ["appx"],
  "application/appxbundle": ["appxbundle"],
  "application/atom+xml": ["atom"],
  "application/atomcat+xml": ["atomcat"],
  "application/atomdeleted+xml": ["atomdeleted"],
  "application/atomsvc+xml": ["atomsvc"],
  "application/atsc-dwd+xml": ["dwd"],
  "application/atsc-held+xml": ["held"],
  "application/atsc-rsat+xml": ["rsat"],
  "application/automationml-aml+xml": ["aml"],
  "application/automationml-amlx+zip": ["amlx"],
  "application/bdoc": ["bdoc"],
  "application/calendar+xml": ["xcs"],
  "application/ccxml+xml": ["ccxml"],
  "application/cdfx+xml": ["cdfx"],
  "application/cdmi-capability": ["cdmia"],
  "application/cdmi-container": ["cdmic"],
  "application/cdmi-domain": ["cdmid"],
  "application/cdmi-object": ["cdmio"],
  "application/cdmi-queue": ["cdmiq"],
  "application/cpl+xml": ["cpl"],
  "application/cu-seeme": ["cu"],
  "application/cwl": ["cwl"],
  "application/dash+xml": ["mpd"],
  "application/dash-patch+xml": ["mpp"],
  "application/davmount+xml": ["davmount"],
  "application/docbook+xml": ["dbk"],
  "application/dssc+der": ["dssc"],
  "application/dssc+xml": ["xdssc"],
  "application/ecmascript": ["ecma"],
  "application/emma+xml": ["emma"],
  "application/emotionml+xml": ["emotionml"],
  "application/epub+zip": ["epub"],
  "application/exi": ["exi"],
  "application/express": ["exp"],
  "application/fdf": ["fdf"],
  "application/fdt+xml": ["fdt"],
  "application/font-tdpfr": ["pfr"],
  "application/geo+json": ["geojson"],
  "application/gml+xml": ["gml"],
  "application/gpx+xml": ["gpx"],
  "application/gxf": ["gxf"],
  "application/gzip": ["gz"],
  "application/hjson": ["hjson"],
  "application/hyperstudio": ["stk"],
  "application/inkml+xml": ["ink", "inkml"],
  "application/ipfix": ["ipfix"],
  "application/its+xml": ["its"],
  "application/java-archive": ["jar", "war", "ear"],
  "application/java-serialized-object": ["ser"],
  "application/java-vm": ["class"],
  "application/javascript": ["*js"],
  "application/json": ["json", "map"],
  "application/json5": ["json5"],
  "application/jsonml+json": ["jsonml"],
  "application/ld+json": ["jsonld"],
  "application/lgr+xml": ["lgr"],
  "application/lost+xml": ["lostxml"],
  "application/mac-binhex40": ["hqx"],
  "application/mac-compactpro": ["cpt"],
  "application/mads+xml": ["mads"],
  "application/manifest+json": ["webmanifest"],
  "application/marc": ["mrc"],
  "application/marcxml+xml": ["mrcx"],
  "application/mathematica": ["ma", "nb", "mb"],
  "application/mathml+xml": ["mathml"],
  "application/mbox": ["mbox"],
  "application/media-policy-dataset+xml": ["mpf"],
  "application/mediaservercontrol+xml": ["mscml"],
  "application/metalink+xml": ["metalink"],
  "application/metalink4+xml": ["meta4"],
  "application/mets+xml": ["mets"],
  "application/mmt-aei+xml": ["maei"],
  "application/mmt-usd+xml": ["musd"],
  "application/mods+xml": ["mods"],
  "application/mp21": ["m21", "mp21"],
  "application/mp4": ["*mp4", "*mpg4", "mp4s", "m4p"],
  "application/msix": ["msix"],
  "application/msixbundle": ["msixbundle"],
  "application/msword": ["doc", "dot"],
  "application/mxf": ["mxf"],
  "application/n-quads": ["nq"],
  "application/n-triples": ["nt"],
  "application/node": ["cjs"],
  "application/octet-stream": [
    "bin",
    "dms",
    "lrf",
    "mar",
    "so",
    "dist",
    "distz",
    "pkg",
    "bpk",
    "dump",
    "elc",
    "deploy",
    "exe",
    "dll",
    "deb",
    "dmg",
    "iso",
    "img",
    "msi",
    "msp",
    "msm",
    "buffer",
  ],
  "application/oda": ["oda"],
  "application/oebps-package+xml": ["opf"],
  "application/ogg": ["ogx"],
  "application/omdoc+xml": ["omdoc"],
  "application/onenote": ["onetoc", "onetoc2", "onetmp", "onepkg"],
  "application/oxps": ["oxps"],
  "application/p2p-overlay+xml": ["relo"],
  "application/patch-ops-error+xml": ["xer"],
  "application/pdf": ["pdf"],
  "application/pgp-encrypted": ["pgp"],
  "application/pgp-keys": ["asc"],
  "application/pgp-signature": ["sig", "*asc"],
  "application/pics-rules": ["prf"],
  "application/pkcs10": ["p10"],
  "application/pkcs7-mime": ["p7m", "p7c"],
  "application/pkcs7-signature": ["p7s"],
  "application/pkcs8": ["p8"],
  "application/pkix-attr-cert": ["ac"],
  "application/pkix-cert": ["cer"],
  "application/pkix-crl": ["crl"],
  "application/pkix-pkipath": ["pkipath"],
  "application/pkixcmp": ["pki"],
  "application/pls+xml": ["pls"],
  "application/postscript": ["ai", "eps", "ps"],
  "application/provenance+xml": ["provx"],
  "application/pskc+xml": ["pskcxml"],
  "application/raml+yaml": ["raml"],
  "application/rdf+xml": ["rdf", "owl"],
  "application/reginfo+xml": ["rif"],
  "application/relax-ng-compact-syntax": ["rnc"],
  "application/resource-lists+xml": ["rl"],
  "application/resource-lists-diff+xml": ["rld"],
  "application/rls-services+xml": ["rs"],
  "application/route-apd+xml": ["rapd"],
  "application/route-s-tsid+xml": ["sls"],
  "application/route-usd+xml": ["rusd"],
  "application/rpki-ghostbusters": ["gbr"],
  "application/rpki-manifest": ["mft"],
  "application/rpki-roa": ["roa"],
  "application/rsd+xml": ["rsd"],
  "application/rss+xml": ["rss"],
  "application/rtf": ["rtf"],
  "application/sbml+xml": ["sbml"],
  "application/scvp-cv-request": ["scq"],
  "application/scvp-cv-response": ["scs"],
  "application/scvp-vp-request": ["spq"],
  "application/scvp-vp-response": ["spp"],
  "application/sdp": ["sdp"],
  "application/senml+xml": ["senmlx"],
  "application/sensml+xml": ["sensmlx"],
  "application/set-payment-initiation": ["setpay"],
  "application/set-registration-initiation": ["setreg"],
  "application/shf+xml": ["shf"],
  "application/sieve": ["siv", "sieve"],
  "application/smil+xml": ["smi", "smil"],
  "application/sparql-query": ["rq"],
  "application/sparql-results+xml": ["srx"],
  "application/sql": ["sql"],
  "application/srgs": ["gram"],
  "application/srgs+xml": ["grxml"],
  "application/sru+xml": ["sru"],
  "application/ssdl+xml": ["ssdl"],
  "application/ssml+xml": ["ssml"],
  "application/swid+xml": ["swidtag"],
  "application/tei+xml": ["tei", "teicorpus"],
  "application/thraud+xml": ["tfi"],
  "application/timestamped-data": ["tsd"],
  "application/toml": ["toml"],
  "application/trig": ["trig"],
  "application/ttml+xml": ["ttml"],
  "application/ubjson": ["ubj"],
  "application/urc-ressheet+xml": ["rsheet"],
  "application/urc-targetdesc+xml": ["td"],
  "application/voicexml+xml": ["vxml"],
  "application/wasm": ["wasm"],
  "application/watcherinfo+xml": ["wif"],
  "application/widget": ["wgt"],
  "application/winhlp": ["hlp"],
  "application/wsdl+xml": ["wsdl"],
  "application/wspolicy+xml": ["wspolicy"],
  "application/xaml+xml": ["xaml"],
  "application/xcap-att+xml": ["xav"],
  "application/xcap-caps+xml": ["xca"],
  "application/xcap-diff+xml": ["xdf"],
  "application/xcap-el+xml": ["xel"],
  "application/xcap-ns+xml": ["xns"],
  "application/xenc+xml": ["xenc"],
  "application/xfdf": ["xfdf"],
  "application/xhtml+xml": ["xhtml", "xht"],
  "application/xliff+xml": ["xlf"],
  "application/xml": ["xml", "xsl", "xsd", "rng"],
  "application/xml-dtd": ["dtd"],
  "application/xop+xml": ["xop"],
  "application/xproc+xml": ["xpl"],
  "application/xslt+xml": ["*xsl", "xslt"],
  "application/xspf+xml": ["xspf"],
  "application/xv+xml": ["mxml", "xhvml", "xvml", "xvm"],
  "application/yang": ["yang"],
  "application/yin+xml": ["yin"],
  "application/zip": ["zip"],
  "audio/3gpp": ["*3gpp"],
  "audio/aac": ["adts", "aac"],
  "audio/adpcm": ["adp"],
  "audio/amr": ["amr"],
  "audio/basic": ["au", "snd"],
  "audio/midi": ["mid", "midi", "kar", "rmi"],
  "audio/mobile-xmf": ["mxmf"],
  "audio/mp3": ["*mp3"],
  "audio/mp4": ["m4a", "mp4a"],
  "audio/mpeg": ["mpga", "mp2", "mp2a", "mp3", "m2a", "m3a"],
  "audio/ogg": ["oga", "ogg", "spx", "opus"],
  "audio/s3m": ["s3m"],
  "audio/silk": ["sil"],
  "audio/wav": ["wav"],
  "audio/wave": ["*wav"],
  "audio/webm": ["weba"],
  "audio/xm": ["xm"],
  "font/collection": ["ttc"],
  "font/otf": ["otf"],
  "font/ttf": ["ttf"],
  "font/woff": ["woff"],
  "font/woff2": ["woff2"],
  "image/aces": ["exr"],
  "image/apng": ["apng"],
  "image/avci": ["avci"],
  "image/avcs": ["avcs"],
  "image/avif": ["avif"],
  "image/bmp": ["bmp", "dib"],
  "image/cgm": ["cgm"],
  "image/dicom-rle": ["drle"],
  "image/dpx": ["dpx"],
  "image/emf": ["emf"],
  "image/fits": ["fits"],
  "image/g3fax": ["g3"],
  "image/gif": ["gif"],
  "image/heic": ["heic"],
  "image/heic-sequence": ["heics"],
  "image/heif": ["heif"],
  "image/heif-sequence": ["heifs"],
  "image/hej2k": ["hej2"],
  "image/hsj2": ["hsj2"],
  "image/ief": ["ief"],
  "image/jls": ["jls"],
  "image/jp2": ["jp2", "jpg2"],
  "image/jpeg": ["jpeg", "jpg", "jpe"],
  "image/jph": ["jph"],
  "image/jphc": ["jhc"],
  "image/jpm": ["jpm", "jpgm"],
  "image/jpx": ["jpx", "jpf"],
  "image/jxl": ["jxl"],
  "image/jxr": ["jxr"],
  "image/jxra": ["jxra"],
  "image/jxrs": ["jxrs"],
  "image/jxs": ["jxs"],
  "image/jxsc": ["jxsc"],
  "image/jxsi": ["jxsi"],
  "image/jxss": ["jxss"],
  "image/ktx": ["ktx"],
  "image/ktx2": ["ktx2"],
  "image/png": ["png"],
  "image/sgi": ["sgi"],
  "image/svg+xml": ["svg", "svgz"],
  "image/t38": ["t38"],
  "image/tiff": ["tif", "tiff"],
  "image/tiff-fx": ["tfx"],
  "image/webp": ["webp"],
  "image/wmf": ["wmf"],
  "message/disposition-notification": ["disposition-notification"],
  "message/global": ["u8msg"],
  "message/global-delivery-status": ["u8dsn"],
  "message/global-disposition-notification": ["u8mdn"],
  "message/global-headers": ["u8hdr"],
  "message/rfc822": ["eml", "mime"],
  "model/3mf": ["3mf"],
  "model/gltf+json": ["gltf"],
  "model/gltf-binary": ["glb"],
  "model/iges": ["igs", "iges"],
  "model/jt": ["jt"],
  "model/mesh": ["msh", "mesh", "silo"],
  "model/mtl": ["mtl"],
  "model/obj": ["obj"],
  "model/prc": ["prc"],
  "model/step+xml": ["stpx"],
  "model/step+zip": ["stpz"],
  "model/step-xml+zip": ["stpxz"],
  "model/stl": ["stl"],
  "model/u3d": ["u3d"],
  "model/vrml": ["wrl", "vrml"],
  "model/x3d+binary": ["*x3db", "x3dbz"],
  "model/x3d+fastinfoset": ["x3db"],
  "model/x3d+vrml": ["*x3dv", "x3dvz"],
  "model/x3d+xml": ["x3d", "x3dz"],
  "model/x3d-vrml": ["x3dv"],
  "text/cache-manifest": ["appcache", "manifest"],
  "text/calendar": ["ics", "ifb"],
  "text/coffeescript": ["coffee", "litcoffee"],
  "text/css": ["css"],
  "text/csv": ["csv"],
  "text/html": ["html", "htm", "shtml"],
  "text/jade": ["jade"],
  "text/javascript": ["js", "mjs"],
  "text/jsx": ["jsx"],
  "text/less": ["less"],
  "text/markdown": ["md", "markdown"],
  "text/mathml": ["mml"],
  "text/mdx": ["mdx"],
  "text/n3": ["n3"],
  "text/plain": ["txt", "text", "conf", "def", "list", "log", "in", "ini"],
  "text/richtext": ["rtx"],
  "text/rtf": ["*rtf"],
  "text/sgml": ["sgml", "sgm"],
  "text/shex": ["shex"],
  "text/slim": ["slim", "slm"],
  "text/spdx": ["spdx"],
  "text/stylus": ["stylus", "styl"],
  "text/tab-separated-values": ["tsv"],
  "text/troff": ["t", "tr", "roff", "man", "me", "ms"],
  "text/turtle": ["ttl"],
  "text/uri-list": ["uri", "uris", "urls"],
  "text/vcard": ["vcard"],
  "text/vtt": ["vtt"],
  "text/wgsl": ["wgsl"],
  "text/xml": ["*xml"],
  "text/yaml": ["yaml", "yml"],
  "video/3gpp": ["3gp", "3gpp"],
  "video/3gpp2": ["3g2"],
  "video/h261": ["h261"],
  "video/h263": ["h263"],
  "video/h264": ["h264"],
  "video/iso.segment": ["m4s"],
  "video/jpeg": ["jpgv"],
  "video/jpm": ["*jpm", "*jpgm"],
  "video/mj2": ["mj2", "mjp2"],
  "video/mp2t": ["ts", "m2t", "m2ts", "mts"],
  "video/mp4": ["mp4", "mp4v", "mpg4"],
  "video/mpeg": ["mpeg", "mpg", "mpe", "m1v", "m2v"],
  "video/ogg": ["ogv"],
  "video/quicktime": ["qt", "mov"],
  "video/webm": ["webm"],
})
export function getFileInfo(href: string) {
  const result: Record<"name" | "ext" | "type" | "filename", string | null> = {
    name: null,
    ext: null,
    type: "unknown",
    filename: null,
  }

  if (!href) {
    return result
  }

  const filename = getUriPathBasename(href, true)

  result.filename = filename
  result.type = getFileType(filename)

  const parts = filename.split(".")
  if (parts.length > 0) {
    result.ext = parts.pop() || null
    result.name = parts.join(".")
  }

  return result
}

export type IFileType =
  | "image"
  | "video"
  | "pdf"
  | "word"
  | "excel"
  | "ppt"
  | "zip"
  | "audio"
  | "exe"
  | "csv"
  | "code"
  | "text"
  | "file"
  | "unknown"

// Uploadable file types for file input components
// Includes both generic types and specific image formats
export const UPLOAD_FILE_TYPES = [
  "file",
  "image",
  "csv",
  "pdf",
  "word",
  "excel",
  "ppt",
  "zip",
  "video",
  "audio",
  "png",
  "jpg",
] as const

export type UploadFileType = typeof UPLOAD_FILE_TYPES[number]

/**
 * Check if a type is a valid upload file type
 */
export function isUploadFileType(type: string): type is UploadFileType {
  return UPLOAD_FILE_TYPES.includes(type as any)
}

// Unified file extension registry - single source of truth
export const unifiedFileTypes: [Exclude<IFileType, "unknown">, Set<string>][] = [
  ["image", new Set(["jpg", "jpeg", "png", "gif", "bmp", "tiff", "webp", "svg", "ico"])],
  ["video", new Set(["mp4", "mov", "avi", "mkv", "flv", "wmv", "webm"])],
  ["pdf", new Set(["pdf"])],
  ["word", new Set(["doc", "docx", "wps"])],
  ["excel", new Set(["xls", "xlsx", "et"])],
  ["ppt", new Set(["ppt", "pptx", "dps"])],
  ["zip", new Set(["zip", "rar", "7z", "tar"])],
  ["audio", new Set(["mp3", "wma", "flac", "aac"])],
  ["exe", new Set(["exe"])],
  ["csv", new Set(["csv"])],
  ["code", new Set(["js", "jsx", "ts", "tsx", "vue", "html", "css", "scss", "less", "php", "py", "rb", "java", "c", "cpp", "go", "rust", "h", "json", "md", "mjs", "yml", "yaml", "xml", "toml", "env", "sh"])],
  ["text", new Set(["txt", "log", "conf", "def", "list", "in", "ini"])],
]

// Maintain backward compatibility with existing fileTypes export
export const fileTypes: [Exclude<IFileType, "unknown" | "code" | "text">, Set<string>][] = [
  ["image", new Set(["jpg", "jpeg", "png", "gif", "bmp", "tiff", "webp", "svg"])],
  ["video", new Set(["mp4", "mov", "avi", "mkv", "flv", "wmv", "webm"])],
  ["pdf", new Set(["pdf"])],
  ["word", new Set(["doc", "docx", "wps"])],
  ["excel", new Set(["xls", "xlsx", "et"])],
  ["ppt", new Set(["ppt", "pptx", "dps"])],
  ["zip", new Set(["zip", "rar", "7z", "tar"])],
  ["audio", new Set(["mp3", "wma", "flac", "aac"])],
  ["exe", new Set(["exe"])],
  ["csv", new Set(["csv"])],
]

export function getFileType(filename?: string, isExtension?: boolean): IFileType {
  if (!filename)
    return "unknown"

  // Extract the file extension from the filename
  const extension = isExtension ? filename : getFileExtensionFromBasename(filename)
  if (!extension)
    return "unknown"

  let result: IFileType = "unknown"
  // Use unified registry for type detection
  unifiedFileTypes.forEach(([type, set]) => {
    if (result !== "unknown")
      return

    if (set.has(extension)) {
      result = type
    }
  })

  // Return 'unknown' if the file type is not recognized
  return result
}

export function getBaseUploadProps(type: string) {
  switch (type) {
    case "csv":
      return { accept: "text/csv" }
    case "pdf":
      return { accept: "application/pdf" }
    case "word":
      return { accept: ".doc,.docx,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document" }
    case "excel":
      return { accept: ".xls,.xlsx,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }
    case "ppt":
      return { accept: ".ppt,.pptx,application/vnd.ms-powerpoint,application/vnd.openxmlformats-officedocument.presentationml.presentation" }
    case "zip":
      return { accept: ".zip,.rar,.7z,.tar,application/zip,application/x-rar-compressed,application/x-7z-compressed" }
    case "image":
      return { accept: "image/*" }
    case "video":
      return { accept: "video/*" }
    case "audio":
      return { accept: "audio/*" }
    case "file":
      return { accept: "*" }
    default:
      return { accept: "*" }
  }
}

export const LANGUAGE_MAP: Record<string, string> = {
  js: "javascript",
  ts: "typescript",
  py: "python",
  java: "java",
  cpp: "cpp",
  c: "c",
  html: "html",
  css: "css",
  json: "json",
  md: "markdown",
  vue: "vue",
  sh: "shell",
  yml: "yaml",
  yaml: "yaml",
  xml: "xml",
  aimd: "aimd",
  toml: "toml",
  env: "env",
}
export const EXTENSION_MAP = Object.fromEntries(Object.entries(LANGUAGE_MAP).map(([ext, lang]) => [lang, ext]))
export const ENV_EXTENSIONS = [".env", ".env.local", ".env.development", ".env.production", ".env.staging", ".env.example"]

export const FILE_TYPES = {
  text: [".txt", ".js", ".ts", ".json", ".html", ".css", ".md", ".vue", ".py", ".java", ".cpp", ".h", ".c", ".sh", ".yml", ".yaml", ".xml", ".toml", "aimd", ...ENV_EXTENSIONS],
  image: [".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp"],
} as const

export function getFileLanguage(filename: string): string {
  if (filename.startsWith(".env"))
    return "dotenv"

  const ext = filename.split(".").pop()?.toLowerCase() || ""
  return LANGUAGE_MAP[ext] || "plaintext"
}

// Icon functionality merged from file-icons.ts
// eslint-disable-next-line ts/no-empty-object-type
type FileIcon = FunctionalComponent<SVGAttributes, {}, any, {}>

export const fileIcons: { [key: string]: FileIcon } = {
  ".tsx": TSXIcon,
  ".jsx": JSIcon,
  ".ts": TSIcon,
  ".json": JSONIcon,
  ".css": CSSIcon,
  ".md": MarkdownIcon,
  ".js": JSIcon,
  ".mjs": MJSIcon,
  ".html": HTMLIcon,
  ".vue": VueIcon,
  ".yml": YAMLIcon,
  ".yaml": YAMLIcon,
  ".png": ImageIcon,
  ".jpg": ImageIcon,
  ".jpeg": ImageIcon,
  ".svg": ImageIcon,
  ".eslint": ESLintIcon,
  ".git": GitIcon,
  ".prettier": PrettierIcon,
  ".py": PythonIcon,
  ".aimd": AIMDIcon,
  ".txt": TextIcon,
  ".pdf": IconFilePdf,
  ".csv": CSVIcon,
  // Office document icons (Tabler - monochrome style)
  ".doc": DocIcon,
  ".docx": DocIcon,
  ".xls": XlsIcon,
  ".xlsx": XlsIcon,
  ".ppt": PptIcon,
  ".pptx": PptIcon,
  ".zip": ZipIcon,
  ".rar": ZipIcon,
  ".7z": ZipIcon,
}

/**
 * Returns the appropriate icon component based on file extension
 * Uses unified file type system
 */
export function getFileCategoryIcon(filename: string, isExtension = false, isType = false) {
  const fileType = isType ? filename : getFileType(filename, isExtension)

  switch (fileType) {
    case "code":
      return IconFileCode
    case "image":
      return IconFileImage
    case "text":
      return IconFileText
    case "pdf":
      return IconFilePdf
    case "csv":
      return CSVIcon
    case "word":
      return DocIcon
    case "excel":
      return XlsIcon
    case "ppt":
      return PptIcon
    case "zip":
      return ZipIcon
    default: {
      // Check for specific extensions that need special handling
      const extension = isExtension ? filename : filename.split(".").pop()?.toLowerCase() || ""

      if (extension === "md") {
        return IconFileMarkdown
      }

      if (extension === "json") {
        return IconFileJson
      }

      return IconFileDocument
    }
  }
}

function getFileIcon(filename: string, isExtension = false): FileIcon {
  const extension = isExtension ? filename : filename.slice(filename.lastIndexOf("."))

  return fileIcons[extension] || getFileCategoryIcon(filename, isExtension) || TextIcon
}

export function getFileSpecificIcon(filename: string, isExtension = false) {
  // Handle special cases first
  if (filename === "package.json")
    return getFileIcon(".json")
  else if (filename === "package-lock.json")
    return getFileIcon(".json")
  else if (filename === "README.md")
    return getFileIcon(".md")
  else if (filename.includes(".eslintrc"))
    return getFileIcon(".eslint")
  else if (filename.includes(".git"))
    return getFileIcon(".git")
  else if (filename.includes(".prettier"))
    return getFileIcon(".prettier")
  else
    return getFileIcon(filename, isExtension)
}

// Legacy extensions arrays for backward compatibility
export const codeExtensions = Array.from(unifiedFileTypes.find(([type]) => type === "code")?.[1] || [])
export const imageExtensions = Array.from(unifiedFileTypes.find(([type]) => type === "image")?.[1] || [])
export const textExtensions = Array.from(unifiedFileTypes.find(([type]) => type === "text")?.[1] || [])

export function getMIMEByName(name: string) {
  const extension = getFileExtensionFromBasename(name)
  if (!extension) {
    return null
  }

  return getMIMEByExtension(extension)
}
export function getMIMEByExtension(extension: string) {
  for (const mime in standardFileTypes) {
    const extensions = standardFileTypes[mime]
    if (extensions.includes(extension)) {
      return mime
    }
  }

  return null
}

/**
 * Determines if a file should be previewed instead of opened in Monaco editor
 * @param filename - The filename to check
 * @returns true if the file should be previewed, false if it should be edited
 */
export function shouldPreviewFile(filename: string): boolean {
  const fileType = getFileType(filename)

  // Files that should be previewed (not edited as text)
  const previewTypes: IFileType[] = [
    "image",
    "video",
    "audio",
    "pdf",
    "word",
    "excel",
    "ppt",
    "zip",
    "exe",
    "csv", // CSV gets special table preview
  ]

  return previewTypes.includes(fileType)
}

/**
 * Determines if a file can be edited as text in Monaco
 * @param filename - The filename to check
 * @returns true if the file can be edited as text
 */
export function canEditAsText(filename: string): boolean {
  return !shouldPreviewFile(filename)
}

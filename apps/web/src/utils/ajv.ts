import Ajv from "ajv"
import addFormats from "ajv-formats"

export const ajv = new Ajv()

// ajv.addKeyword("rn_built_in_type")
// ajv.addKeyword("build_in_rv_type")
ajv.addKeyword("file_extension")
ajv.addKeyword("link")
ajv.addKeyword("airalogy_type")
/** @deprecated use airalogy_type instead */
ajv.addKeyword("airalogy_built_in_type")
ajv.addKeyword("recommended_protocol_id")

addFormats(ajv, ["date", "time", "date-time", "duration", "uri", "uri-reference", "uri-template", "url", "email", "hostname", "ipv4", "ipv6", "regex", "uuid", "json-pointer", "json-pointer-uri-fragment", "relative-json-pointer", "byte", "int32", "int64", "float", "double", "password", "binary"])

import type { AxiosError, AxiosResponse } from "axios"
import { handleUnauthorized } from "@/utils/auth/unauthorized"
import { createStreamRequest } from "@/utils/axios"
import { localStg } from "@/utils/storage"
import { renderMessageContent } from "@airalogy/composables/useClosableMessage"
import { baseURL } from "."

const decoder = new TextDecoder("utf-8")
/**
 * Creates a request instance specifically configured for streaming responses
 */
export const streamRequest = createStreamRequest<ReadableStream>(
  {
    baseURL,
    headers: {},
    responseType: "stream",
  },
  {
    onRequest(config) {
      const { headers } = config

      // set token
      const token = localStg.get("token")
      Object.assign(headers, { "Auth-Token": token })

      return config
    },

    // Custom transformation for streaming responses
    async transformBackendResponse(response: AxiosResponse<any>) {
      // Log response structure to debug
      console.log("Response type:", typeof response.data)
      console.log("Response properties:", Object.keys(response.data || {}))
      console.log("Response headers:", response.headers)

      // Handle different types of response data
      let result = ""

      // If response.data is a string, return it directly
      if (typeof response.data === "string") {
        return response.data
      }

      // If response.data is already a readable stream with getReader method
      if (response.data && typeof response.data.getReader === "function") {
        const reader = response.data.getReader()

        while (true) {
          const { done, value } = await reader.read()
          if (done)
            break
          result += decoder.decode(value, { stream: true })
        }

        result += decoder.decode()
        return result
      }

      // Handle various possible response objects with streaming capabilities
      const possibleStreamObjects = [
        response.data,
        response.request,
        response.request?.responseText,
        response,
      ]

      for (const obj of possibleStreamObjects) {
        // Skip if undefined or null
        if (!obj)
          continue

        // Check if this object has an 'on' method for event handling
        if (typeof (obj as any).on === "function") {
          const streamObj = obj as any

          return new Promise<string>((resolve, reject) => {
            const chunks: Uint8Array[] = []

            streamObj.on("data", (chunk: Uint8Array) => {
              chunks.push(chunk)
            })

            streamObj.on("end", () => {
              try {
                const concatenated = new Uint8Array(
                  chunks.reduce((acc, chunk) => acc + chunk.length, 0),
                )

                let offset = 0
                for (const chunk of chunks) {
                  concatenated.set(chunk, offset)
                  offset += chunk.length
                }

                result = decoder.decode(concatenated)
                resolve(result)
              }
              catch (err) {
                reject(err)
              }
            })

            streamObj.on("error", (err: Error) => {
              reject(err)
            })
          })
        }
      }

      // If the data is a response-like object with text() method
      if (response.data && typeof response.data.text === "function") {
        try {
          return await response.data.text()
        }
        catch (e) {
          console.error("Error calling text() method:", e)
        }
      }

      // Last resort: try to convert to string
      return String(response.data)
    },

    isBackendSuccess(response) {
      return response.status === 200
    },

    onError(error: AxiosError, cancelAllRequest) {
      if (error.response?.status === 401) {
        cancelAllRequest()
        handleUnauthorized()
      }

      if (error.code === "ERR_CANCELED") {
        return
      }

      const { showError = true } = error.config?.metadata || {}

      if (showError) {
        const message = error.message
        window.$message?.error(renderMessageContent(typeof message === "string" ? message : JSON.stringify(message, null, 2)), { duration: 0, closable: true },
        )
      }
    },
  },
)

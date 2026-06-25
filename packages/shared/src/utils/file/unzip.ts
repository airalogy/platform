import { type AsyncUnzipOptions, type AsyncZipOptions, type AsyncZippable, unzip, type Unzipped, zip, zipSync } from "fflate"

export function unzipToPromise(data: Uint8Array, opts: AsyncUnzipOptions): Promise<Unzipped> {
  if (!("Promise" in window)) {
    throw new Error("zipToPromise requires promises.  Use `zip` to support older browsers.")
  }

  return new Promise(
    (resolve, reject) => unzip(
      data,
      opts,
      (error, result) => {
        if (error) {
          reject(error)
        }
        else {
          resolve(result)
        }
      },
    ),
  )
}
export function zipToPromise(data: AsyncZippable, opts: AsyncZipOptions) {
  return new Promise<Uint8Array>((resolve, reject) => {
    zip(data, opts, (error, result) => {
      if (error) {
        reject(error)
      }
      else {
        resolve(result)
      }
    })
  })
}

const decoder = new TextDecoder()
export function arrayBufferToString(binArray: Uint8Array) {
  return decoder.decode(binArray)
}

export type { Zippable } from "fflate"

export { unzip, zip, zipSync }

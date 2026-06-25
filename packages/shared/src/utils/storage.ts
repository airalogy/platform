import localforage from "localforage"

/** The storage type */
export type StorageType = "local" | "session"
interface StorageData<T = any> {
  data: T
  expire: number | null
}

const DEFAULT_CACHE_TIME = 60 * 60 * 24 * 30

export function createStorage<T extends object>(
  type: StorageType,
  expire: number | null = DEFAULT_CACHE_TIME,
) {
  const stg = type === "session" ? window.sessionStorage : window.localStorage

  const storage = {
    /**
     * Set session
     *
     * @param key Session key
     * @param value Session value
     */
    set<K extends keyof T>(key: K, value: T[K]) {
      const data: StorageData = {
        data: value,
        expire: expire !== null ? new Date().getTime() + expire * 1000 : null,
      }
      const json = JSON.stringify(data)

      stg.setItem(key as string, json)
    },
    /**
     * Get session
     *
     * @param key Session key
     */
    get<K extends keyof T>(key: K, returnNullExpire: boolean = true): T[K] | null {
      const json = stg.getItem(key as string)
      if (json) {
        let storageData: StorageData<T[K]> | null = null

        try {
          storageData = JSON.parse(json)
        }
        catch { }

        if (storageData) {
          const { data, expire: dataExpire } = storageData
          if (
            (returnNullExpire && dataExpire === null)
            || (dataExpire !== null && dataExpire >= Date.now())
          ) {
            return data
          }
        }
      }

      stg.removeItem(key as string)

      return null
    },
    remove(key: keyof T) {
      stg.removeItem(key as string)
    },
    clear() {
      stg.clear()
    },
  }
  return storage
}

type LocalForage<T extends object> = Omit<
  typeof localforage,
  "getItem" | "setItem" | "removeItem"
> & {
  getItem: <K extends keyof T>(
    key: K,
    callback?: (err: any, value: T[K] | null) => void,
  ) => Promise<T[K] | null>

  setItem: <K extends keyof T>(
    key: K,
    value: T[K],
    callback?: (err: any, value: T[K]) => void,
  ) => Promise<T[K]>

  removeItem: (key: keyof T, callback?: (err: any) => void) => Promise<void>
}

type LocalforageDriver = "local" | "indexedDB" | "webSQL"

const driverMap: Record<LocalforageDriver, string> = {
  local: localforage.LOCALSTORAGE,
  indexedDB: localforage.INDEXEDDB,
  webSQL: localforage.WEBSQL,
}
export function createLocalforage<T extends object>(driver: LocalforageDriver, name: string) {
  localforage.config({
    driver: driverMap[driver],
    name,
  })

  return localforage as LocalForage<T>
}

// export const localStg = createStorage<StorageType.Local>("local")
// export const sessionStg = createStorage<StorageType.Session>("session")

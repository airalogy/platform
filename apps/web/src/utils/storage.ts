import type { AppStorage } from "../types/storage"
import { createStorage } from "@airalogy/shared/utils"

export const localStg = createStorage<AppStorage.Local>("local", null)
export const localStgWithExpire = createStorage<AppStorage.Local>("local")

// export const sessionStg = createStorage<StorageType.Session>("session")

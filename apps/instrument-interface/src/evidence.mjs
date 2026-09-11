import { Buffer } from "node:buffer"
import { constants } from "node:fs"
import { lstat, mkdir, mkdtemp, open, realpath } from "node:fs/promises"
import { isAbsolute, join } from "node:path"
import { canonical, digest, MAX_BYTES } from "./contract.mjs"

export async function syncDirectory(path) {
  const handle = await open(path, constants.O_RDONLY | constants.O_DIRECTORY | constants.O_NOFOLLOW)
  try {
    await handle.sync()
  }
  finally {
    await handle.close()
  }
}

export async function readPrivateSelection(path, limit = MAX_BYTES) {
  if (!isAbsolute(path))
    throw new Error("Select an absolute local path")
  const handle = await open(path, constants.O_RDONLY | constants.O_NOFOLLOW)
  try {
    const info = await handle.stat()
    if (!info.isFile() || info.size > limit)
      throw new Error("Selected file is not a bounded regular file")
    const bytes = Buffer.alloc(info.size + 1)
    const { bytesRead } = await handle.read(bytes, 0, bytes.length, 0)
    if (bytesRead !== info.size)
      throw new Error("Selected file changed while reading")
    return bytes.subarray(0, bytesRead)
  }
  finally {
    await handle.close()
  }
}

export class Evidence {
  static async create(root, preview) {
    if (process.platform === "win32")
      throw new Error("Windows private-file ACL support is not qualified yet")
    if (!isAbsolute(root))
      throw new Error("Select an absolute private evidence directory")
    await mkdir(root, { mode: 0o700, recursive: true })
    const info = await lstat(root)
    if (!info.isDirectory() || info.isSymbolicLink() || (info.mode & 0o077) || info.uid !== process.getuid())
      throw new Error("Evidence parent must be an owner-only directory (0700)")
    const parent = await realpath(root)
    const directory = await mkdtemp(join(parent, "interface-"))
    await syncDirectory(parent)
    const evidence = new Evidence(directory)
    await evidence.write("preview.json", Buffer.from(canonical(preview)))
    return evidence
  }

  constructor(directory) {
    this.directory = directory
    this.sequence = 0
    this.previous = null
    this.appendTail = Promise.resolve()
  }

  async write(name, bytes) {
    if (!/^[a-z0-9.-]+$/.test(name))
      throw new Error("Invalid evidence name")
    const file = await open(join(this.directory, name), "wx", 0o600)
    try {
      await file.writeFile(bytes)
      await file.sync()
    }
    finally {
      await file.close()
    }
    // Flush the new name too, before treating an intent/receipt as published.
    await syncDirectory(this.directory)
  }

  async append(kind, data) {
    // Capture caller-owned data before queueing. Stop/close callbacks may race,
    // but each sequence and its predecessor are published by one writer only.
    const selected = JSON.parse(canonical({ kind, data }))
    const next = this.appendTail.then(async () => {
      const event = { sequence: this.sequence, previous: this.previous, time: new Date().toISOString(), ...selected }
      const sha256 = digest(event)
      await this.write(`${String(this.sequence).padStart(4, "0")}.json`, Buffer.from(canonical({ ...event, sha256 })))
      this.sequence += 1
      this.previous = sha256
      return sha256
    })
    // A partial/failed write poisons the chain; never retry its name, skip a
    // sequence or acknowledge subsequent evidence as durably recorded.
    this.appendTail = next
    return next
  }
}

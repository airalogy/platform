import assert from "node:assert/strict"
import { execFileSync } from "node:child_process"
import { randomBytes, randomUUID } from "node:crypto"
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { prepareObjectStorage, storageTestImage } from "./prepare-object-storage.mjs"

// Only uniquely named, isolated fixtures are touched. No host ports, existing
// volumes or production credentials are used. A legacy source, when requested,
// runs on a new empty fixture volume; the destination never opens its data.
const options = process.argv.slice(2)
if (options.length && (options.length !== 2 || options[0] !== "--legacy-image" || !/^[\w./:@-]+$/.test(options[1])))
  throw new Error("Usage: object-storage-acceptance.mjs [--legacy-image <locally-available-image>]")
prepareObjectStorage({ verifyOnly: true })
const sourceImage = options[1] || storageTestImage
const prefix = `platform-storage-test-${randomUUID()}`
const fixture = mkdtempSync(join(tmpdir(), "platform-storage-test-"))
const password = randomBytes(24).toString("hex")
const servers = [`${prefix}-source`, `${prefix}-restore`]
// Docker resource names can exceed DNS's 63-byte label limit. Short aliases are
// safe because each acceptance run owns its own isolated network.
const aliases = ["source", "restored"]
const clientName = `${prefix}-client`
const noProxy = ["-e", "NO_PROXY=*", "-e", "no_proxy=*"]
const docker = (args, timeout = 120_000) => execFileSync("docker", args, { encoding: "utf8", timeout, killSignal: "SIGKILL", stdio: ["ignore", "pipe", "pipe"], maxBuffer: 8 * 1024 * 1024 })
function client(args, seconds = 110) {
  return docker(["exec", clientName, "timeout", "-k", "2", String(seconds), "mc", ...args], (seconds + 5) * 1000)
}
let cleaned = false
process.once("exit", cleanup)
process.once("SIGINT", () => process.exit(130))
process.once("SIGTERM", () => process.exit(143))

try {
  docker(["network", "create", "--internal", prefix])
  for (const [index, name] of servers.entries()) {
    docker(["run", "--pull=never", "--detach", "--name", name, "--network", prefix, "--network-alias", aliases[index], "-e", "MINIO_ROOT_USER=fixture", "-e", `MINIO_ROOT_PASSWORD=${password}`, index === 0 ? sourceImage : storageTestImage, "server", "/data", "--address", ":9200", "--console-address", ":9201"])
  }
  docker(["run", "--detach", "--name", clientName, "--network", prefix, ...noProxy, "--user", `${process.getuid()}:${process.getgid()}`, "-e", "MC_CONFIG_DIR=/tmp/mc", "--mount", `type=bind,src=${fixture},dst=/fixtures`, "-e", `MC_HOST_source=http://fixture:${password}@source:9200`, "-e", `MC_HOST_restored=http://fixture:${password}@restored:9200`, "--entrypoint", "sleep", storageTestImage, "900"])
  for (const alias of aliases) {
    let ready = false
    let lastError = ""
    const deadline = Date.now() + 45_000
    while (Date.now() < deadline) {
      try {
        client(["ready", alias], 5)
        ready = true
        break
      }
      catch (error) {
        lastError = String(error.stderr || error.message).replaceAll(password, "[redacted]")
        await new Promise(resolve => setTimeout(resolve, 1000))
      }
    }
    assert.ok(ready, `${alias} did not become ready: ${lastError}`)
  }
  console.log("Object storage servers ready; checking reads, writes and access controls.")
  const file = "量表 data.csv"
  const content = "subject_id,score\nsynthetic-001,12\n"
  writeFileSync(join(fixture, file), content)
  // Larger than the client's default part size; verify the multipart ETag below.
  const binary = randomBytes(67 * 1024 * 1024)
  writeFileSync(join(fixture, "multipart.bin"), binary)
  client(["mb", "source/records"])
  client(["mb", "restored/records"])
  client(["cp", `/fixtures/${file}`, "source/records/"])
  client(["cp", "/fixtures/multipart.bin", "source/records/"])
  assert.match(JSON.parse(client(["stat", "--json", "source/records/multipart.bin"])).etag, /-\d+$/)
  assert.equal(client(["cat", `source/records/${file}`]), content)

  const anonymous = `http://source:9200/records/${encodeURIComponent(file)}`
  const assertForbidden = url => docker(["run", "--rm", "--network", prefix, ...noProxy, "--entrypoint", "sh", storageTestImage, "-ec", "if wget -S -O /tmp/result \"$1\" 2>/tmp/error; then exit 1; fi; grep -q \"403 Forbidden\" /tmp/error", "sh", url])
  const denied = assertForbidden(anonymous)
  assert.equal(denied, "")
  const shared = JSON.parse(client(["share", "download", "--json", "--expire", "1m", `source/records/${file}`]).trim())
  assert.ok(shared.share, "signed download URL was not returned")
  assert.equal(docker(["run", "--rm", "--network", prefix, ...noProxy, "--entrypoint", "wget", storageTestImage, "-qO-", shared.share]), content)

  client(["mirror", "source/records", "/fixtures/backup/"])
  assert.equal(readFileSync(join(fixture, "backup", file), "utf8"), content)
  assert.deepEqual(readFileSync(join(fixture, "backup/multipart.bin")), binary)
  client(["rm", `source/records/${file}`])
  client(["mirror", "/fixtures/backup/", "restored/records"])
  assert.equal(client(["cat", `restored/records/${file}`]), content)
  assertForbidden(`http://restored:9200/records/${encodeURIComponent(file)}`)
  client(["cp", "restored/records/multipart.bin", "/fixtures/restored.bin"])
  assert.deepEqual(readFileSync(join(fixture, "restored.bin")), binary)
  const lock = readFileSync(new URL("../deploy/object-storage/sources.env", import.meta.url), "utf8")
  for (const binaryName of ["minio", "mc"]) {
    const release = new RegExp(`^${binaryName.toUpperCase()}_RELEASE=(.+)$`, "m").exec(lock)[1]
    assert.ok(docker(["run", "--rm", "--entrypoint", binaryName, storageTestImage, "--version"]).includes(release))
  }
  docker(["run", "--rm", "--entrypoint", "sh", storageTestImage, "-ec", "test -s /licenses/minio/LICENSE; test -s /licenses/mc/LICENSE; cd /usr/share/airalogy-object-storage/source; . ./sources.env; printf '%s  minio-upstream.tar.gz\\n%s  mc-upstream.tar.gz\\n' \"$MINIO_SOURCE_SHA256\" \"$MC_SOURCE_SHA256\" | sha256sum -c -; test -s minio-vendored.tar.gz; test -s mc-vendored.tar.gz"])
  console.log("Object storage: upload, multipart, private access, signed download, fresh-server logical restore and source identity passed.")
}
finally {
  cleanup()
}

function cleanup() {
  if (cleaned)
    return
  cleaned = true
  // Explicit fixture names only; never prune Docker or delete existing volumes.
  for (const name of [clientName, ...servers]) {
    try {
      docker(["rm", "--force", "--volumes", name], 10_000)
    }
    catch { /* A fixture may not have started. */ }
  }
  try {
    docker(["network", "rm", prefix], 10_000)
  }
  catch { /* A failed network creation does not authorize deleting anything else. */ }
  rmSync(fixture, { recursive: true, force: true })
}

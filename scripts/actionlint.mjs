import { execFileSync } from "node:child_process"
import { createHash } from "node:crypto"
import { existsSync, mkdirSync, mkdtempSync, readFileSync, renameSync, rmSync, writeFileSync } from "node:fs"
import { join } from "node:path"
import { fileURLToPath, pathToFileURL } from "node:url"

// Official v1.7.12 archives checked against the published release checksums.
// Also pin extracted bytes, so a modified cache is never silently executed.
export const version = "1.7.12"
export const pins = {
  darwin_amd64: ["5b44c3bc2255115c9b69e30efc0fecdf498fdb63c5d58e17084fd5f16324c644", "d1f7cee75ae2873609bd9567b4600bebc5315a5e733e73202987a44fafdd53b2"],
  darwin_arm64: ["aba9ced2dee8d27fecca3dc7feb1a7f9a52caefa1eb46f3271ea66b6e0e6953f", "8db11704dc296f096216db4db65d86cd7f0ebfdf4c38453a1da276b137b88388"],
  linux_amd64: ["8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8", "c872d6db8c6bf83a8eaa704fc93999f027d55dffbc63b8a6abdccb47df5f4cd4"],
  linux_arm64: ["325e971b6ba9bfa504672e29be93c24981eeb1c07576d730e9f7c8805afff0c6", "ac0323433c2853ec3fb978c611430c5b3dc5d43c58d1a1ec031b00ab572beb60"],
}
const repositoryRoot = fileURLToPath(new URL("../", import.meta.url))

export function targetFor(platform = process.platform, arch = process.arch) {
  const target = `${platform}_${arch === "x64" ? "amd64" : arch}`
  if (!pins[target])
    throw new Error(`Unsupported actionlint host: ${target}; use Linux/macOS x64 or arm64`)
  return target
}

export function verifyDigest(bytes, expected) {
  if (createHash("sha256").update(bytes).digest("hex") !== expected)
    throw new Error("actionlint checksum mismatch; refusing to execute or install")
  return bytes
}

export function actionlintPath() {
  return join(repositoryRoot, ".cache", "actionlint", version, targetFor(), "actionlint")
}

export function requireActionlint(executable = actionlintPath()) {
  if (!existsSync(executable))
    throw new Error("Pinned actionlint is missing. Run pnpm ci:tools:install once, then retry. Checks never install tools implicitly.")
  verifyDigest(readFileSync(executable), pins[targetFor()][1])
  return executable
}

function install() {
  if (existsSync(actionlintPath())) {
    requireActionlint()
    return
  }
  const target = targetFor()
  const directory = join(repositoryRoot, ".cache", "actionlint", version, target)
  mkdirSync(directory, { recursive: true })
  const temporary = mkdtempSync(join(directory, "download-"))
  try {
    const name = `actionlint_${version}_${target}.tar.gz`
    const archive = join(temporary, name)
    execFileSync("curl", ["--fail", "--location", "--proto", "=https", "--proto-redir", "=https", "--max-time", "90", "--retry", "2", "--output", archive, `https://github.com/rhysd/actionlint/releases/download/v${version}/${name}`], { stdio: "inherit" })
    verifyDigest(readFileSync(archive), pins[target][0])
    // Extract only this member to memory, never archive paths onto the filesystem.
    const binary = execFileSync("tar", ["-xzOf", archive, "actionlint"], { maxBuffer: 32 * 1024 * 1024 })
    verifyDigest(binary, pins[target][1])
    const staged = join(temporary, "actionlint")
    writeFileSync(staged, binary, { flag: "wx", mode: 0o755 })
    renameSync(staged, actionlintPath())
    console.log(`Installed verified actionlint ${version} in the repository's ignored cache.`)
  }
  finally {
    rmSync(temporary, { recursive: true, force: true })
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  if (process.argv[2] === "--install" && process.argv.length === 3)
    install()
  else if (process.argv.length === 2)
    // Keep results independent of optional tools installed on a developer's PATH.
    // This is workflow/expression checking, not a substitute for shell/runtime tests.
    execFileSync(requireActionlint(), ["-shellcheck=", "-pyflakes="], { cwd: repositoryRoot, stdio: "inherit" })
  else
    throw new Error("Usage: node scripts/actionlint.mjs [--install]")
}

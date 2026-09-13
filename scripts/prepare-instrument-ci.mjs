import { execFileSync } from "node:child_process"
import { chmodSync, existsSync, readFileSync, realpathSync, statSync } from "node:fs"
import { createRequire } from "node:module"
import { pathToFileURL } from "node:url"

// CI preparation only. Never relax the runtime's executable integrity checks.
export function chmodArguments(path) {
  if (!path.startsWith("/") || path.includes("\0"))
    throw new Error("chmod requires an absolute executable path")
  return ["go-w", path]
}

export function hardenExecutable(selected) {
  const path = realpathSync(selected)
  const info = statSync(path)
  if (!info.isFile() || !(info.mode & 0o111) || ![0, process.getuid()].includes(info.uid))
    throw new Error("Expected an independently installed executable owned by root or the runner")
  if (info.mode & 0o022) {
    console.log(`Removing group/world write permission from ${path} (mode ${(info.mode & 0o777).toString(8)})`)
    if (info.uid === process.getuid())
      chmodSync(path, info.mode & 0o777 & ~0o022)
    else
      // realpath is absolute, so it cannot be parsed as an option. BSD chmod
      // does not accept GNU's post-mode "--" argument.
      execFileSync("sudo", ["chmod", ...chmodArguments(path)], { stdio: "inherit" })
  }
  if (statSync(path).mode & 0o022)
    throw new Error("Executable permissions remain unsafe")
  return path
}

export function browserProfile(paths) {
  if (!paths.length || paths.some(path => !/^\/[\w./-]+$/.test(path)))
    throw new Error("AppArmor needs exact absolute executable paths without pattern syntax")
  // Chromium's documented per-executable exception, not a global sysctl change.
  // Both the browser sandbox and all other applications' restrictions stay on.
  return `abi <abi/4.0>,\n${paths.map((path, index) => `profile airalogy-ci-chromium-${index} "${path}" flags=(unconfined) {\n  userns,\n}\n`).join("")}`
}

async function main() {
  if (process.env.GITHUB_ACTIONS !== "true" || process.env.RUNNER_ENVIRONMENT !== "github-hosted")
    throw new Error("This preparation is restricted to disposable GitHub-hosted runners")
  const flags = process.argv.slice(2)
  if (!flags.length || flags.some(flag => !["--executables", "--browser"].includes(flag)))
    throw new Error("Select --executables and/or --browser")
  if (flags.includes("--executables")) {
    hardenExecutable(process.execPath)
    hardenExecutable(execFileSync("python3", ["-c", "import sys; print(sys.executable)"], { encoding: "utf8" }).trim())
    hardenExecutable(execFileSync("which", ["gh"], { encoding: "utf8" }).trim())
  }
  if (flags.includes("--browser")) {
    const require = createRequire(new URL("../apps/instrument-interface/package.json", import.meta.url))
    const runtimeRequire = createRequire(require.resolve("playwright/package.json"))
    const { registry } = runtimeRequire("playwright-core/lib/coreBundle").registry
    const paths = ["chromium", "chromium-headless-shell"].map(name => realpathSync(registry.findExecutable(name).executablePath()))
    const restriction = "/proc/sys/kernel/apparmor_restrict_unprivileged_userns"
    if (process.platform === "linux" && existsSync(restriction) && readFileSync(restriction, "utf8").trim() === "1") {
      console.log("Allowing user namespaces for the two exact CI Chromium executables only")
      execFileSync("sudo", ["apparmor_parser", "-r"], { input: browserProfile(paths), stdio: ["pipe", "inherit", "inherit"] })
    }
    // Fail early with browser diagnostics from an empty synthetic page. Product
    // sessions keep private evidence private and never print vendor page data.
    const { chromium } = require("playwright")
    const browser = await chromium.launch({ headless: true, chromiumSandbox: true })
    try {
      const page = await browser.newPage()
      await page.setContent("<title>Airalogy CI sandbox check</title>")
      if (await page.title() !== "Airalogy CI sandbox check")
        throw new Error("Sandboxed browser readiness check failed")
      console.log("Sandboxed Chromium is ready; no external application was opened")
    }
    finally {
      await browser.close()
    }
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href)
  await main()

import { execFileSync } from "node:child_process"
import { mkdtempSync, readFileSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { fileURLToPath } from "node:url"
import { computeTestImage, prepareComputeTestImage } from "./compute-runner-integration.mjs"

// Build the real release wheel: fabricated test SDK versions cannot detect
// stale compatibility declarations in the source-included example packages.
const cwd = fileURLToPath(new URL("../", import.meta.url))
const version = readFileSync(new URL("../VERSION", import.meta.url), "utf8").trim()
const directory = mkdtempSync(join(tmpdir(), "platform-gateway-sandbox-"))
try {
  prepareComputeTestImage()
  execFileSync("uv", ["--directory", "apps/instrument-gateway", "build", "--out-dir", directory], { cwd, stdio: "inherit", timeout: 300_000 })
  execFileSync("python3", ["-m", "unittest", "discover", "-s", "tests", "-p", "test_package*.py", "-v"], {
    cwd: fileURLToPath(new URL("../apps/instrument-gateway/", import.meta.url)),
    stdio: "inherit",
    timeout: 600_000,
    env: { ...process.env, PYTHONPATH: "src", RUN_ADAPTER_SANDBOX_TESTS: "1", ADAPTER_TEST_IMAGE: computeTestImage, ADAPTER_TEST_SDK_WHEEL: join(directory, `airalogy_instrument_gateway-${version}-py3-none-any.whl`) },
  })
}
finally {
  rmSync(directory, { recursive: true, force: true })
}

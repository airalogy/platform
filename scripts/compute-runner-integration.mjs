import { spawnSync } from "node:child_process"
import { fileURLToPath, pathToFileURL } from "node:url"

// A reviewed multi-platform image shared by local pre-push and hosted CI.
// The synthetic test never contacts Platform, an AI provider, or an instrument.
export const computeTestImage = "python@sha256:eb43ff125d8d58d7449dcba7d336c23bcac412f526d861db493b9994d8010280"
const cwd = fileURLToPath(new URL("../", import.meta.url))

function run(command, args, options = {}) {
  const result = spawnSync(command, args, { cwd, stdio: "inherit", timeout: 300_000, ...options })
  if (result.error)
    throw result.error
  if (result.status !== 0)
    process.exit(result.status ?? 1)
}

export function prepareComputeTestImage() {
  run("docker", ["version"])
  const installed = spawnSync("docker", ["image", "inspect", computeTestImage], { cwd, stdio: "ignore", timeout: 30_000 })
  if (installed.error)
    throw installed.error
  if (installed.status !== 0)
    run("docker", ["pull", computeTestImage])
  return {
    COMPUTE_ENGINE_TEST: "1",
    COMPUTE_TEST_IMAGE: computeTestImage,
    COMPUTE_TEST_HELPER_IMAGE: computeTestImage,
    COMPUTE_TEST_BACKEND: "docker",
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const engineEnvironment = prepareComputeTestImage()
  run("python3", ["-m", "unittest", "discover", "-s", "apps/compute-runner/tests", "-p", "test_engine_integration.py", "-v"], {
    env: { ...process.env, ...engineEnvironment, PYTHONPATH: "apps/compute-runner/src" },
  })
}

/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { readFileSync } from "node:fs"
import test from "node:test"

test("object restore stops at failed credentials instead of masking errors and mirroring", () => {
  const restore = readFileSync("deploy/single-lab/scripts/restore.sh", "utf8")
  const command = /-ec '([^']+)'/.exec(restore)?.[1]
  assert.ok(command)
  const result = spawnSync("sh", ["-ec", `mc() { printf '%s\\n' "$1" >&2; return 17; }; ${command}`], { encoding: "utf8" })
  assert.equal(result.status, 17)
  assert.equal(result.stderr.trim(), "alias")
  for (const file of ["backup", "restore"]) {
    const source = readFileSync(`deploy/single-lab/scripts/${file}.sh`, "utf8")
    assert.ok(source.includes("--user \"$(id -u):$(id -g)\""))
    assert.ok(source.includes("--env MC_CONFIG_DIR=/tmp/airalogy-mc"))
  }
})

test("storage upgrade guard blocks unknown or different engines before data operations", () => {
  const script = `source deploy/single-lab/scripts/lib.sh
compose() { printf 'fixture-container'; }
docker() {
  if [[ "$*" == *'{{.Image}}'* ]]; then printf 'current';
  elif [[ "$*" == *'{{.Id}}'* ]]; then printf '%s' "$TARGET_ID";
  elif [[ "\${*: -1}" == current ]]; then printf '%s' "$CURRENT_COMMIT";
  else printf '%s' "$TARGET_COMMIT"; fi
}
verify_object_storage_compatibility target
`
  const commit = "a".repeat(40)
  for (const [current, target, id, success] of [[commit, commit, "new", true], ["", "", "current", true], ["", commit, "new", false], [commit, "b".repeat(40), "new", false]]) {
    const result = spawnSync("bash", ["-eu", "-c", script], { encoding: "utf8", env: { ...process.env, CURRENT_COMMIT: current, TARGET_COMMIT: target, TARGET_ID: id } })
    assert.equal(result.status === 0, success, result.stderr)
    if (!success)
      assert.match(result.stderr, /engine change blocked/)
  }
  const upgrade = readFileSync("deploy/single-lab/scripts/upgrade.sh", "utf8")
  assert.ok(upgrade.indexOf("verify_object_storage_compatibility") < upgrade.indexOf("backup_path=\""))
  const rollback = readFileSync("deploy/single-lab/scripts/rollback.sh", "utf8")
  for (const file of ["upgrade", "start"])
    assert.match(readFileSync(`deploy/single-lab/scripts/${file}.sh`, "utf8"), /do not rebuild over an upstream or custom image name/)
  assert.ok(rollback.indexOf("restore_storage_snapshot") < rollback.indexOf("\"$SCRIPT_DIR/restore.sh\""))
})

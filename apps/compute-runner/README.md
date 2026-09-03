# Airalogy Compute Runner

The Compute Runner is an independently supervised execution plane for approval-gated Airalogy Compute Jobs. It pulls signed jobs from Platform, verifies the complete envelope again, downloads only lease-authorized DataAsset versions, and executes reviewed Python or R source in a short-lived OCI container. Platform's API process never evaluates job source and never receives access to the container-engine socket.

## Security boundary

The reference Runner accepts only immutable `image@sha256:<digest>` job and helper images. Research containers run as UID/GID `65532`, with a read-only root filesystem, all capabilities dropped, `no-new-privileges`, a PID limit, CPU and memory limits, and no host bind mounts. Inputs and output use a job-specific, size-limited tmpfs volume managed by Docker or Podman. The Runner verifies every downloaded byte count and SHA-256 digest before staging it.

Network policy fails closed. `none` maps to the engine's isolated network. An `egress_allowlist` job runs only when its exact, sorted comma-separated host set is mapped in `AIRALOGY_COMPUTE_EGRESS_NETWORKS_JSON` to an independently administered container network that enforces that allowlist. Merely creating a normal bridge network is not sufficient.

Container-engine access is a privileged local boundary. Prefer a dedicated rootless Podman account or a dedicated Runner host. Do not mount its socket into Platform API containers, and do not co-locate untrusted services under the Runner identity.

## Source and result contract

The selected Compute Environment image must provide `python` for Python jobs or `Rscript` for R jobs. The Runner exposes:

- `AIRALOGY_INPUT_JSON=/airalogy/input/input.json`
- `AIRALOGY_INPUT_DIR=/airalogy/input`
- `AIRALOGY_RESULT_JSON=/airalogy/output/result.json`

The source must write one UTF-8 JSON object to `AIRALOGY_RESULT_JSON`. Platform validates it against the immutable result Schema before accepting completion. A request may also declare up to 16 output files. Source writes each one to `/airalogy/output/files/<declared-mount-name>`; the Runner rejects undeclared references, missing required files, per-file or combined size overflow, and content that changes while being streamed. It computes SHA-256 inside the read-only helper, streams the bytes through the job lease, and Platform registers a Project-visible draft DataAsset only after the structured result and every receipt pass final validation.

The reference Runner disables the research container log driver and discards untrusted standard output so code cannot bypass the output limit and fill host storage; use the bounded result object for diagnostics that must be retained. The immutable helper image must provide `tar`, `test`, `wc`, `sha256sum`, and `cat`.

## Configuration

Create a Runner in **Lab resource library → Compute environments**, copy its one-time credential, and bind it only to reviewed Compute Environment revisions. Install the exact helper image locally before startup (for example, a reviewed BusyBox image pinned by digest).

```bash
export AIRALOGY_PLATFORM_URL=https://lab.example.edu
export AIRALOGY_COMPUTE_RUNNER_TOKEN=aicr_replace_with_one_time_credential
export AIRALOGY_COMPUTE_BACKEND=podman
export AIRALOGY_COMPUTE_HELPER_IMAGE=registry.example.edu/airalogy/compute-helper@sha256:replace
export AIRALOGY_COMPUTE_STATE_FILE=/var/lib/airalogy-compute-runner/state.json
airalogy-compute-runner
```

Additional settings:

- `AIRALOGY_COMPUTE_EGRESS_NETWORKS_JSON`: exact host-set keys to preconfigured enforcement network names.
- `AIRALOGY_COMPUTE_POLL_SECONDS`, `AIRALOGY_COMPUTE_HEARTBEAT_SECONDS`, and `AIRALOGY_COMPUTE_REQUEST_TIMEOUT_SECONDS`.
- `AIRALOGY_COMPUTE_OUTPUT_UPLOAD_TIMEOUT_SECONDS`: bounded timeout for streaming a declared result file back to Platform.
- `AIRALOGY_COMPUTE_STOP_TIMEOUT_SECONDS`: local grace period before stop is considered unsafe.
- `AIRALOGY_COMPUTE_MAX_WORKSPACE_BYTES`: hard local ceiling over input, source, and approved output capacity.
- `AIRALOGY_COMPUTE_ALLOW_INSECURE_HTTP=true`: test-only escape hatch for an isolated non-loopback network.

The state journal contains the short lease and reviewed source. It is atomically written with mode `0600`; keep its parent directory private and persistent. After restart, a possibly running container is stopped before any new work is accepted. Completion, failure, and cancellation acknowledgements are replayed when safe; an expired or rejected callback is reconciled fail-closed by Platform.

`deploy/airalogy-compute-runner.service` and `deploy/compute-runner.env.example` provide a hardened systemd starting point. The template intentionally leaves Linux namespaces available because rootless Podman needs a user namespace; the research container itself receives the isolation flags described above. `PrivateDevices=true` makes the default unit CPU-only, so GPU deployments need a reviewed device-specific systemd override as well as Platform approval. Review the service account's Podman/Docker access and the preconfigured egress networks as security-sensitive infrastructure.

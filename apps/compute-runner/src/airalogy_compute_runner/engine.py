"""Container-engine boundary for isolated, immutable Compute Jobs."""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import subprocess
import tarfile
from dataclasses import dataclass
from pathlib import Path

from .config import RunnerConfig
from .models import ComputeJobEnvelope


class EngineError(RuntimeError):
    """The local container isolation contract could not be satisfied."""


@dataclass
class JobProcess:
    process: subprocess.Popen[bytes]
    container_name: str
    volume_name: str


class ContainerEngine:
    def __init__(self, config: RunnerConfig):
        self.config = config
        executable = shutil.which(config.backend)
        if executable is None:
            raise EngineError(f"Container backend {config.backend!r} is not installed")
        self.executable = str(Path(executable).resolve())

    def _run(
        self,
        arguments: list[str],
        *,
        input_bytes: bytes | None = None,
        timeout: float = 60,
        check: bool = True,
    ) -> subprocess.CompletedProcess[bytes]:
        process = subprocess.run(
            [self.executable, *arguments],
            input=input_bytes,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        if check and process.returncode != 0:
            message = process.stderr.decode("utf-8", errors="replace")[-4000:]
            raise EngineError(
                f"{self.config.backend} {' '.join(arguments[:3])} failed: {message}"
            )
        return process

    def verify(self) -> None:
        self._run(["version"], timeout=15)
        self._run(["image", "inspect", self.config.helper_image], timeout=30)

    @staticmethod
    def names(job_id: str) -> tuple[str, str]:
        suffix = hashlib.sha256(job_id.encode("utf-8")).hexdigest()[:24]
        return f"airalogy-job-{suffix}", f"airalogy-work-{suffix}"

    def network_for(self, job: ComputeJobEnvelope) -> str:
        if job.network_policy == "none":
            if job.allowed_egress_hosts:
                raise EngineError(
                    "Network-disabled job unexpectedly declares egress hosts"
                )
            return "none"
        if not job.allowed_egress_hosts:
            raise EngineError("Egress policy requires at least one exact host")
        network = self.config.egress_networks.get(job.egress_key)
        if not network:
            raise EngineError(
                "No independently enforced network is configured for the exact egress host set"
            )
        return network

    def create_workspace(self, job: ComputeJobEnvelope) -> tuple[str, str]:
        if job.workspace_bytes > self.config.max_workspace_bytes:
            raise EngineError("Compute Job exceeds the local workspace limit")
        container_name, volume_name = self.names(job.job_id)
        self.cleanup(container_name, volume_name)
        self._run(
            [
                "volume",
                "create",
                "--driver",
                "local",
                "--opt",
                "type=tmpfs",
                "--opt",
                "device=tmpfs",
                "--opt",
                f"o=size={job.workspace_bytes}",
                volume_name,
            ],
            timeout=30,
        )
        return container_name, volume_name

    @staticmethod
    def _directory(name: str, mode: int, uid: int = 0, gid: int = 0) -> tarfile.TarInfo:
        entry = tarfile.TarInfo(name)
        entry.type = tarfile.DIRTYPE
        entry.mode = mode
        entry.uid = uid
        entry.gid = gid
        entry.mtime = 0
        return entry

    @staticmethod
    def _bytes_entry(
        archive: tarfile.TarFile,
        name: str,
        value: bytes,
        *,
        mode: int = 0o444,
    ) -> None:
        entry = tarfile.TarInfo(name)
        entry.size = len(value)
        entry.mode = mode
        entry.uid = 0
        entry.gid = 0
        entry.mtime = 0
        archive.addfile(entry, io.BytesIO(value))

    def populate_workspace(
        self,
        job: ComputeJobEnvelope,
        volume_name: str,
        input_files: dict[str, Path],
    ) -> None:
        command = [
            self.executable,
            "run",
            "--rm",
            "--interactive",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--mount",
            f"type=volume,source={volume_name},target=/airalogy",
            "--entrypoint",
            "tar",
            self.config.helper_image,
            "-xpf",
            "-",
            "-C",
            "/airalogy",
        ]
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        if process.stdin is None:
            process.kill()
            raise EngineError("Unable to open helper input stream")
        try:
            with tarfile.open(fileobj=process.stdin, mode="w|") as archive:
                archive.addfile(self._directory("source", 0o555))
                archive.addfile(self._directory("input", 0o555))
                archive.addfile(self._directory("output", 0o700, 65532, 65532))
                extension = "py" if job.language == "python" else "R"
                self._bytes_entry(
                    archive,
                    f"source/main.{extension}",
                    job.source_code.encode("utf-8"),
                )
                self._bytes_entry(
                    archive,
                    "input/input.json",
                    json.dumps(
                        job.input_payload,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8"),
                )
                for input_item in job.inputs:
                    path = input_files[input_item.id]
                    archive.add(
                        path,
                        arcname=f"input/{input_item.mount_name}",
                        recursive=False,
                        filter=lambda info: self._safe_input_info(info),
                    )
            process.stdin = None
            _stdout, stderr = process.communicate(timeout=120)
        except Exception:
            process.kill()
            process.wait()
            raise
        if process.returncode != 0:
            message = stderr.decode("utf-8", errors="replace")[-4000:]
            raise EngineError(f"Failed to stage Compute workspace: {message}")

    @staticmethod
    def _safe_input_info(info: tarfile.TarInfo) -> tarfile.TarInfo:
        info.mode = 0o444
        info.uid = 0
        info.gid = 0
        info.uname = ""
        info.gname = ""
        info.mtime = 0
        return info

    def start(
        self, job: ComputeJobEnvelope, container_name: str, volume_name: str
    ) -> JobProcess:
        network = self.network_for(job)
        command = [
            self.executable,
            "run",
            "--name",
            container_name,
            "--rm",
            "--log-driver",
            "none",
            "--init",
            "--user",
            "65532:65532",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            "256",
            "--memory",
            f"{job.memory_mb}m",
            "--memory-swap",
            f"{job.memory_mb}m",
            "--cpus",
            f"{job.cpu_millis / 1000:.3f}",
            "--network",
            network,
            "--mount",
            f"type=volume,source={volume_name},target=/airalogy",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,nodev,size=67108864,uid=65532,gid=65532,mode=0700",
            "--workdir",
            "/airalogy/output",
            "--env",
            "AIRALOGY_INPUT_JSON=/airalogy/input/input.json",
            "--env",
            "AIRALOGY_INPUT_DIR=/airalogy/input",
            "--env",
            "AIRALOGY_RESULT_JSON=/airalogy/output/result.json",
        ]
        if job.gpu_count:
            command.extend(["--gpus", str(job.gpu_count)])
        executable = "python" if job.language == "python" else "Rscript"
        extension = "py" if job.language == "python" else "R"
        command.extend(
            [
                "--entrypoint",
                executable,
                job.image_ref,
                f"/airalogy/source/main.{extension}",
            ]
        )
        process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return JobProcess(process, container_name, volume_name)

    def stop(self, container_name: str) -> None:
        self._run(
            [
                "stop",
                "--time",
                str(int(self.config.stop_timeout_seconds)),
                container_name,
            ],
            timeout=self.config.stop_timeout_seconds + 10,
            check=False,
        )
        inspection = self._run(
            ["inspect", "--format", "{{.State.Running}}", container_name],
            timeout=15,
            check=False,
        )
        if inspection.returncode == 0 and inspection.stdout.strip() == b"true":
            raise EngineError("Compute container did not stop within the local timeout")

    def stderr_tail(self, _process: JobProcess, _limit: int = 8000) -> str:
        return "untrusted container standard output was discarded by policy"

    def read_result(
        self, job: ComputeJobEnvelope, volume_name: str
    ) -> tuple[dict, int]:
        base = [
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--mount",
            f"type=volume,source={volume_name},target=/airalogy,readonly",
        ]
        size_result = self._run(
            [
                *base,
                "--entrypoint",
                "wc",
                self.config.helper_image,
                "-c",
                "/airalogy/output/result.json",
            ],
            timeout=30,
        )
        try:
            size = int(size_result.stdout.decode("ascii").strip().split()[0])
        except (ValueError, IndexError, UnicodeDecodeError) as error:
            raise EngineError("Helper returned an invalid result size") from error
        if size > job.max_output_bytes:
            raise EngineError("Compute result exceeds the approved output limit")
        result = self._run(
            [
                *base,
                "--entrypoint",
                "cat",
                self.config.helper_image,
                "/airalogy/output/result.json",
            ],
            timeout=30,
        ).stdout
        if len(result) != size:
            raise EngineError("Compute result changed while it was being read")
        try:
            value = json.loads(result.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise EngineError("Compute result is not valid UTF-8 JSON") from error
        if not isinstance(value, dict):
            raise EngineError("Compute result must be a JSON object")
        return value, size

    def cleanup(self, container_name: str, volume_name: str) -> None:
        if container_name:
            self._run(["rm", "--force", container_name], timeout=30, check=False)
        if volume_name:
            self._run(["volume", "rm", "--force", volume_name], timeout=30, check=False)

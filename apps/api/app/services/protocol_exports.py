"""Export the immutable source package, never the executor's mutable directory."""

import stat
import zipfile
from pathlib import Path, PurePosixPath

from airalogy.archive import pack_protocol_archive, validate_archive
from airalogy.markdown import extract_assigner_blocks

MAX_PACKAGE_BYTES = 100 * 1024 * 1024
MAX_PACKAGE_FILES = 4096


def build_protocol_export(source: Path, workspace: Path, output_format: str) -> Path:
    if output_format not in {"aira", "zip"}:
        raise ValueError("Unsupported Protocol export format")
    if source.stat().st_size > MAX_PACKAGE_BYTES:
        raise ValueError("Protocol package exceeds export size limit")
    target = workspace / "protocol"
    target.mkdir()
    with zipfile.ZipFile(source) as archive:
        members = archive.infolist()
        if (
            len(members) > MAX_PACKAGE_FILES
            or sum(m.file_size for m in members) > MAX_PACKAGE_BYTES
        ):
            raise ValueError("Protocol package exceeds export limits")
        files = [m for m in members if not m.is_dir()]
        roots = [
            PurePosixPath(m.filename).parent
            for m in files
            if PurePosixPath(m.filename).name == "protocol.aimd"
        ]
        if len(roots) != 1:
            raise ValueError("Expected one Protocol root")
        root = roots[0]
        seen = set()
        for member in files:
            path = PurePosixPath(member.filename)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in member.filename
                or stat.S_ISLNK(member.external_attr >> 16)
            ):
                raise ValueError("Unsafe Protocol package member")
            if not path.is_relative_to(root):
                raise ValueError("File outside Protocol root")
            relative = path.relative_to(root)
            if relative in seen:
                raise ValueError("Duplicate Protocol package member")
            seen.add(relative)
            # Secrets, interpreter caches and generated runtime files are not assets.
            if any(
                part.startswith(".") or part == "__pycache__" for part in relative.parts
            ):
                continue
            if relative.name == "tmp_aimd_model.py" or relative.suffix in {
                ".pyc",
                ".log",
            }:
                continue
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.read(member))
    # Older Platform versions persisted the exact inline Python extraction too.
    # Remove only a provably redundant generated copy, never independent code.
    assigner = target / "assigner.py"
    inline = extract_assigner_blocks(
        (target / "protocol.aimd").read_text(encoding="utf-8")
    )
    generated = "\n\n".join(
        block.get("code", "") if isinstance(block, dict) else block for block in inline
    )
    if (
        generated.strip()
        and assigner.is_file()
        and assigner.read_text(encoding="utf-8").strip() == generated.strip()
    ):
        assigner.unlink()
    output = workspace / f"protocol.{output_format}"
    if output_format == "aira":
        pack_protocol_archive(target, output)
        valid, errors = validate_archive(output)
        if not valid:
            raise ValueError("Invalid Protocol archive: " + "; ".join(map(str, errors)))
    else:
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(target.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(target).as_posix())
    return output

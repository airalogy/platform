import asyncio
import json
import logging
import os
import queue
import shutil
import sys
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

from airalogy_engine import AiralogyEngine

from app.config import config
from app.models.protocol_version import ProtocolVersion

# 创建线程安全的队列
package_download_queue = queue.Queue()
is_downloading = False
logger = logging.getLogger("app")

PROTOCOL_ENGINE_IDLE_SECONDS = 120
PROTOCOL_ENGINE_DEBUG_LOG_FILE = "protocol_debug.log"
SUPPORTED_PROTOCOL_ACTIONS = {
    "get_protocol_info",
    "var_assign",
    "var_validate",
    "import_records",
}

_FIELD_KEY_MAP = {
    "var": "vars",
    "quiz": "quizzes",
    "step": "steps",
    "check": "checks",
    "ref_var": "ref_vars",
    "ref_step": "ref_steps",
    "ref_fig": "ref_figs",
    "cite": "cites",
    "assigner": "assigners",
}


@dataclass
class _ProtocolEnginePoolEntry:
    engine: AiralogyEngine
    protocol_path: str
    boxlite_home: str | None
    last_active: float
    active_calls: int = 0
    cleanup_task: asyncio.Task | None = None


_protocol_engine_pool: dict[str, _ProtocolEnginePoolEntry] = {}
_protocol_engine_pool_lock = asyncio.Lock()


def unzip_file(zip_file, dest_dir: str | Path):
    """
    Unzip a zip file to a destination dir path.
    note:
    1. if the zip file contains a top-level directory, it will remove the top-level directory.
    2. if the dest_dir exists, it will be removed before extracting the zip file.
    """
    dest_path = Path(dest_dir)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_file, "r") as zip_ref:
        wrap_dir = None
        for name in zip_ref.namelist():
            path = Path(name)
            if path.is_dir():
                continue
            if path.name == "protocol.aimd":
                if len(path.parts) > 1:
                    wrap_dir = path.parent
                break

        with tempfile.TemporaryDirectory() as tmp_dir:
            zip_ref.extractall(tmp_dir)
            protocol_root_path = f"{tmp_dir}/{wrap_dir}" if wrap_dir else tmp_dir
            if dest_path.exists():
                shutil.rmtree(dest_path)
            shutil.move(protocol_root_path, dest_path)

    return str(dest_path)


def zip_dir(directory, zip_file_path):
    """zip a directory to a zip file"""
    if zip_file_path.endswith(".zip"):
        zip_file_path = zip_file_path[:-4]
    if directory.endswith("/"):
        directory = directory[:-1]
    root_dir = os.path.dirname(directory)
    base_dir = os.path.basename(directory)
    shutil.make_archive(
        base_name=zip_file_path,
        format="zip",
        root_dir=root_dir,
        base_dir=base_dir,
    )


def remove_exclude_files(directory):
    """remove exclude files and dirs from a directory"""
    exclude_dirs = {"__pycache__"}
    exclude_files = {".env", ".DS_Store"}
    for root, dirs, files in os.walk(directory, topdown=True):
        for dir in dirs:
            if dir in exclude_dirs or dir.startswith("."):
                shutil.rmtree(os.path.join(root, dir))
        for file in files:
            if file in exclude_files or file.startswith(".") or file.endswith(".pyc"):
                os.remove(os.path.join(root, file))


async def prepare_protocol_package(protocol_version: ProtocolVersion):
    # add protocol to download queue
    package_download_queue.put(protocol_version)
    global is_downloading
    if is_downloading:
        return
    is_downloading = True
    try:
        while not package_download_queue.empty():
            protocol_version = package_download_queue.get()
            await download_package(protocol_version)
    finally:
        is_downloading = False


async def download_package(protocol_version: ProtocolVersion):
    # download package from file server if protocol is not in protocols directory
    package_name = protocol_version.package_name
    protocol_dir = config.PROTOCOL_DIR
    protocol_path = f"{protocol_dir}/{package_name}"
    if os.path.exists(protocol_path):
        return

    # donwload protocol package and unzip it to protocol path
    with tempfile.TemporaryDirectory() as tmp_dir:
        pkg_path = f"{tmp_dir}/tmp_{package_name}.zip"
        await protocol_version.download_package(pkg_path)
        unzip_file(pkg_path, protocol_path)
    remove_exclude_files(protocol_path)


def _protocol_path(package_name: str) -> str:
    return str((Path(config.PROTOCOL_DIR) / package_name).expanduser().resolve())


def _sanitize_env_vars(env_vars: dict | None) -> dict[str, str]:
    if env_vars is None:
        return {}
    return {
        str(key): str(value) for key, value in env_vars.items() if value is not None
    }


def _normalize_protocol_info_result(result: dict) -> dict:
    data = result.get("data")
    if not isinstance(data, dict):
        return result

    fields = data.get("fields")
    if not isinstance(fields, dict):
        return result

    normalized_fields = {
        new_key: fields.get(new_key, fields.get(old_key, []))
        for old_key, new_key in _FIELD_KEY_MAP.items()
    }
    known_keys = set(_FIELD_KEY_MAP) | set(_FIELD_KEY_MAP.values())
    for key, value in fields.items():
        if key not in known_keys:
            normalized_fields[key] = value
    data["fields"] = normalized_fields
    return result


def _loop_time() -> float:
    return asyncio.get_running_loop().time()


async def _stop_protocol_engine_entry(
    key: str, entry: _ProtocolEnginePoolEntry
) -> None:
    started_at = time.perf_counter()
    logger.info(
        "Stopping AiralogyEngine: protocol_path=%s active_calls=%s",
        key,
        entry.active_calls,
    )
    try:
        await entry.engine.stop()
    except Exception:
        logger.exception(
            "Failed to stop AiralogyEngine: protocol_path=%s",
            key,
        )
    logger.info(
        "Stopped AiralogyEngine: protocol_path=%s elapsed_ms=%.2f",
        key,
        (time.perf_counter() - started_at) * 1000,
    )


async def _close_protocol_engine_entry(
    key: str, entry: _ProtocolEnginePoolEntry
) -> None:
    started_at = time.perf_counter()
    logger.info(
        "Closing AiralogyEngine: protocol_path=%s active_calls=%s",
        key,
        entry.active_calls,
    )
    try:
        await entry.engine.close()
    except Exception:
        logger.exception(
            "Failed to close AiralogyEngine: protocol_path=%s",
            key,
        )
    logger.info(
        "Closed AiralogyEngine: protocol_path=%s elapsed_ms=%.2f",
        key,
        (time.perf_counter() - started_at) * 1000,
    )


async def _cleanup_idle_protocol_engine(key: str, expected_last_active: float) -> None:
    try:
        await asyncio.sleep(PROTOCOL_ENGINE_IDLE_SECONDS)
    except asyncio.CancelledError:
        return

    entry_to_close: _ProtocolEnginePoolEntry | None = None
    async with _protocol_engine_pool_lock:
        entry = _protocol_engine_pool.get(key)
        if (
            entry is None
            or entry.active_calls > 0
            or entry.last_active != expected_last_active
        ):
            return
        entry.cleanup_task = None
        entry_to_close = _protocol_engine_pool.pop(key)

    logger.info(
        "AiralogyEngine idle timeout reached: protocol_path=%s idle_seconds=%s",
        key,
        PROTOCOL_ENGINE_IDLE_SECONDS,
    )
    await _stop_protocol_engine_entry(key, entry_to_close)
    await _close_protocol_engine_entry(key, entry_to_close)


async def _acquire_protocol_engine(
    package_name: str,
) -> tuple[str, _ProtocolEnginePoolEntry]:
    protocol_path = _protocol_path(package_name)
    key = protocol_path
    async with _protocol_engine_pool_lock:
        entry = _protocol_engine_pool.get(key)
        if entry is None:
            started_at = time.perf_counter()
            boxlite_home = config.AIRALOGY_ENGINE_BOXLITE_HOME
            logger.info(
                "Creating AiralogyEngine: package_name=%s protocol_path=%s image=%s auto_stop=%s debug=%s",
                package_name,
                protocol_path,
                config.AIRALOGY_ENGINE_IMAGE,
                False,
                config.AIRALOGY_ENGINE_DEBUG,
            )
            entry = _ProtocolEnginePoolEntry(
                engine=AiralogyEngine(
                    protocol_path,
                    boxlite_home=boxlite_home,
                    image=config.AIRALOGY_ENGINE_IMAGE,
                    auto_stop=False,
                ),
                protocol_path=protocol_path,
                boxlite_home=boxlite_home,
                last_active=_loop_time(),
            )
            _protocol_engine_pool[key] = entry
            logger.info(
                "Created AiralogyEngine: package_name=%s protocol_path=%s auto_stop=%s elapsed_ms=%.2f",
                package_name,
                protocol_path,
                False,
                (time.perf_counter() - started_at) * 1000,
            )
        else:
            logger.info(
                "Reusing AiralogyEngine: package_name=%s protocol_path=%s active_calls=%s",
                package_name,
                key,
                entry.active_calls,
            )

        if entry.cleanup_task is not None and not entry.cleanup_task.done():
            entry.cleanup_task.cancel()
        entry.cleanup_task = None
        entry.active_calls += 1
        return key, entry


async def _release_protocol_engine(key: str) -> None:
    async with _protocol_engine_pool_lock:
        entry = _protocol_engine_pool.get(key)
        if entry is None:
            return

        entry.active_calls = max(entry.active_calls - 1, 0)
        entry.last_active = _loop_time()
        if entry.active_calls == 0:
            if entry.cleanup_task is not None and not entry.cleanup_task.done():
                entry.cleanup_task.cancel()
            entry.cleanup_task = asyncio.create_task(
                _cleanup_idle_protocol_engine(key, entry.last_active)
            )


async def close_protocol_engine_pool() -> None:
    entries: list[tuple[str, _ProtocolEnginePoolEntry]]
    async with _protocol_engine_pool_lock:
        entries = list(_protocol_engine_pool.items())
        _protocol_engine_pool.clear()
        for _, entry in entries:
            if entry.cleanup_task is not None and not entry.cleanup_task.done():
                entry.cleanup_task.cancel()
            entry.cleanup_task = None

    logger.info("Closing AiralogyEngine pool: entries=%s", len(entries))
    await asyncio.gather(
        *(_close_protocol_engine_entry(key, entry) for key, entry in entries),
        return_exceptions=True,
    )
    logger.info("Closed AiralogyEngine pool: entries=%s", len(entries))


async def protocol_exec_in_engine(
    action: str,
    package_name: str,
    params: dict | None = None,
) -> dict:
    raw_params = params
    params = {} if params is None else params
    if action not in SUPPORTED_PROTOCOL_ACTIONS:
        return {
            "success": False,
            "message": f"Protocol action `{action}` is not supported by AiralogyEngine protocol_exec",
        }

    key, entry = await _acquire_protocol_engine(package_name)
    protocol_path = _protocol_path(package_name)
    started_at = time.perf_counter()
    try:
        logger.info(
            "Executing AiralogyEngine action: action=%s package_name=%s protocol_path=%s debug=%s log_file=%s",
            action,
            package_name,
            protocol_path,
            config.AIRALOGY_ENGINE_DEBUG,
            PROTOCOL_ENGINE_DEBUG_LOG_FILE,
        )
        if action == "get_protocol_info":
            result = await entry.engine.parse_protocol(
                env_vars=_sanitize_env_vars(params.get("env_vars")),
                debug=config.AIRALOGY_ENGINE_DEBUG,
                log_file=PROTOCOL_ENGINE_DEBUG_LOG_FILE,
            )
            result = _normalize_protocol_info_result(result)

        elif action == "var_assign":
            result = await entry.engine.assign_variable(
                var_name=params["var_name"],
                dependent_data=params.get("dependent_data", {}),
                env_vars=_sanitize_env_vars(params.get("env_vars")),
                debug=config.AIRALOGY_ENGINE_DEBUG,
                log_file=PROTOCOL_ENGINE_DEBUG_LOG_FILE,
            )

        elif action == "var_validate":
            result = await entry.engine.validate_variables(
                raw_params,
                debug=config.AIRALOGY_ENGINE_DEBUG,
                log_file=PROTOCOL_ENGINE_DEBUG_LOG_FILE,
            )

        elif action == "import_records":
            result = await entry.engine.import_records(
                input_filename=params["input_filename"],
                input_format=params.get("input_format", "auto"),
                allow_extra_var_fields=bool(
                    params.get("allow_extra_var_fields", False)
                ),
                require_complete_quiz=bool(params.get("require_complete_quiz", False)),
                include_template_defaults=bool(
                    params.get("include_template_defaults", True)
                ),
                validate_model_sync=bool(params.get("validate_model_sync", True)),
                env_vars=_sanitize_env_vars(params.get("env_vars")),
                debug=config.AIRALOGY_ENGINE_DEBUG,
                log_file=PROTOCOL_ENGINE_DEBUG_LOG_FILE,
            )

        else:
            result = {
                "success": False,
                "message": f"Protocol action `{action}` is not supported by AiralogyEngine protocol_exec",
            }

        logger.info(
            "Executed AiralogyEngine action: action=%s package_name=%s success=%s elapsed_ms=%.2f message=%s",
            action,
            package_name,
            result.get("success") if isinstance(result, dict) else None,
            (time.perf_counter() - started_at) * 1000,
            result.get("message") if isinstance(result, dict) else None,
        )
        return result
    except Exception as e:
        logger.exception(
            "AiralogyEngine action failed: action=%s package_name=%s elapsed_ms=%.2f",
            action,
            package_name,
            (time.perf_counter() - started_at) * 1000,
        )
        return {
            "success": False,
            "message": str(e),
            "error_type": type(e).__name__,
        }
    finally:
        await _release_protocol_engine(key)


async def protocol_exec(action: str, package_name: str, params: dict = {}) -> dict:
    # 创建子进程
    if config.PROTOCOL_RUN_ENV == "engine":
        return await protocol_exec_in_engine(action, package_name, params)
    elif config.PROTOCOL_RUN_ENV == "docker":
        cmd = [
            "docker",
            "run",
            "--rm",
            "--cpus=1",
            "--memory=512m",
            "--add-host=airalogy-server-host:host-gateway",
            "-v",
            f"{os.getcwd()}/protocol_executor.py:/home/deploy/app/protocol_executor.py",
            "-v",
            f"{os.getcwd()}/protocols/{package_name}/:/home/deploy/app/protocols/{package_name}/",
            "-v",
            f"{os.getcwd()}/protocol_executor.log:/home/deploy/app/protocol_executor.log",
            "airalogy-protocol-executor:latest",
            "python",
            "protocol_executor.py",
            action,
            package_name,
            json.dumps(params, separators=(",", ":")),
        ]
    else:
        cmd = [
            sys.executable,
            "protocol_executor.py",
            action,
            package_name,
            json.dumps(params, separators=(",", ":")),
        ]

    print(f"protocol_exec, cmd: {cmd}")
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    # 等待子进程完成并获取输出
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        print(
            f"Subprocess failed with package_name: {package_name}, action: {action}, return code {process.returncode}, output: {stdout.decode().strip()}"
        )
        # 如果子进程返回非零状态码,表示发生错误
        return {
            "success": False,
            "message": f"Subprocess failed with return code {process.returncode}",
            "output": stderr.decode().strip(),
        }

    result = stdout.decode().strip()
    try:
        print(result)
        json_result = json.loads(result)
    except json.JSONDecodeError:
        return {
            "success": False,
            "message": "Invalid JSON output from protocol runner",
            "output": result,
        }

    return json_result

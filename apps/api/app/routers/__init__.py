import logging
import logging.config
import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import ORJSONResponse

# from rich.logging import RichHandler
from sqlalchemy.exc import SQLAlchemyError

from app.config import config
from app.libs.protocol_agent import close_protocol_engine_pool
from app.libs.safe_logging import (
    safe_json_body,
    safe_path,
    safe_query_string,
    safe_request_target,
)

from .airalogy_api import router as airalogy_router
from .access import router as access_router
from .airalogy_files import router as airalogy_files_router
from .aira_imports import router as aira_imports_router
from .answers import router as answers_router
from .attachments import router as attachments_router
from .chats import router as chats_router
from .editor import router as editor_router
from .groups import router as groups_router
from .health import router as health_router
from .hub import router as hub_router
from .instance import router as instance_router
from .labs import router as labs_router
from .login import router as login_router
from .oauth import router as oauth_router
from .pinned_items import router as pinned_items_router
from .project_groups import router as project_groups_router
from .projects import router as projects_router
from .protocol_folders import router as protocol_folders_router
from .protocol_users import router as protocol_users_router
from .protocol_versions import router as protocol_versions_router
from .protocols import router as protocols_router
from .questions import router as questions_router
from .records import router as records_router
from .search import router as search_router
from .seo import router as seo_router
from .stars import router as stars_router
from .user_aliases import router as user_aliases_router
from .users import router as users_router
from .workflow import router as workflow_router

if config.APP_ENV != "production":
    from .dev_fixtures import router as dev_fixtures_router

log_path = Path(config.LOG_FILE)
log_path.parent.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await close_protocol_engine_pool()


app = FastAPI(
    default_response_class=ORJSONResponse,
    root_path=config.API_ROOT_PATH,
    lifespan=lifespan,
)

# 使用 ContextVar 来在请求的生命周期中传递 request_id
request_id_var = ContextVar("request_id", default=None)


# 自定义一个 Filter，为所有日志记录添加 request_id
class RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = request_id_var.get()
        return True


class RedactAccessLogFilter(logging.Filter):
    def filter(self, record):
        if record.name == "uvicorn.access" and isinstance(record.args, tuple):
            args = list(record.args)
            if len(args) >= 3:
                args[2] = safe_request_target(str(args[2]))
                record.args = tuple(args)
        return True


LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id_filter": {
            "()": RequestIdFilter,
        },
        "redact_access_log_filter": {
            "()": RedactAccessLogFilter,
        },
    },
    "formatters": {
        # 文件日志格式化器
        "file_formatter": {
            "format": "%(asctime)s - %(levelname)s - [%(request_id)s] - %(message)s",
        },
        # 控制台日志使用 rich 默认格式，更美观
        "console_formatter": {
            "format": "%(asctime)s - [%(request_id)s] - %(message)s",
        },
    },
    "handlers": {
        # 控制台处理器，使用 rich 实现语法高亮
        "console": {
            "class": "rich.logging.RichHandler",
            "formatter": "console_formatter",
            "level": config.LOG_LEVEL,
            "filters": ["request_id_filter", "redact_access_log_filter"],
            "rich_tracebacks": True,  # 开启漂亮的 Traceback
            "tracebacks_show_locals": False,
        },
        # 文件处理器，将日志写入文件
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "file_formatter",
            "filename": str(log_path),
            "level": config.LOG_LEVEL,
            "filters": ["request_id_filter", "redact_access_log_filter"],
            "maxBytes": config.LOG_MAX_BYTES,
            "backupCount": config.LOG_BACKUP_COUNT,
            "encoding": "utf-8",
        },
    },
    "loggers": {
        # uvicorn 访问日志
        "uvicorn.access": {
            "handlers": ["console", "file"],
            "level": config.LOG_LEVEL,
            "propagate": False,
        },
        # uvicorn 错误日志
        "uvicorn.error": {
            "handlers": ["console", "file"],
            "level": config.LOG_LEVEL,
            "propagate": False,
        },
        # sqlalchemy 引擎日志
        "sqlalchemy.engine": {
            "handlers": ["console", "file"],
            "level": config.SQL_LOG_LEVEL,
            "propagate": False,
        },
        # 应用自身的日志
        "app": {
            "handlers": ["console", "file"],
            "level": config.LOG_LEVEL,
            "propagate": False,
        },
    },
}

# 应用日志配置
logging.config.dictConfig(LOGGING_CONFIG)
# 获取我们应用自己的 logger
logger = logging.getLogger("app")


@app.middleware("http")
async def logger_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request_id_var.set(request_id)
    request.state.request_id = request_id
    body = ""
    if (
        config.LOG_REQUEST_BODIES
        and request.headers.get("content-type", "").startswith("application/json")
    ):
        request_body = await request.body()
        body = safe_json_body(request_body)

    log = f"{request.method} {safe_path(request['path'])}"
    query = safe_query_string(str(request.query_params))
    if query:
        log += f" query: {query}"
    if body != "":
        log += f" body: {body}"
    logger.info(log)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
    logger.exception("Database request failed")
    detail = "Database request failed" if config.APP_ENV == "production" else repr(exc)
    return ORJSONResponse(status_code=400, content={"detail": detail})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled request failed")
    request_id = getattr(request.state, "request_id", None) or request_id_var.get()
    detail = {
        "code": "internal_server_error",
        "message": "The server could not complete this request.",
        "request_id": request_id,
    }
    headers = {"X-Request-ID": request_id} if request_id else None
    return ORJSONResponse(status_code=500, content={"detail": detail}, headers=headers)


app.include_router(login_router)
app.include_router(access_router)
app.include_router(instance_router)
app.include_router(health_router)
app.include_router(oauth_router)
app.include_router(attachments_router)
app.include_router(users_router)
app.include_router(labs_router)
app.include_router(projects_router)
app.include_router(groups_router)
app.include_router(protocols_router)
app.include_router(protocol_versions_router)
app.include_router(records_router)
app.include_router(airalogy_files_router)
app.include_router(airalogy_router)
app.include_router(aira_imports_router)
app.include_router(questions_router)
app.include_router(answers_router)
app.include_router(search_router)
app.include_router(seo_router)
app.include_router(chats_router)
app.include_router(editor_router)
app.include_router(hub_router)
app.include_router(stars_router)
app.include_router(user_aliases_router)
app.include_router(project_groups_router)
app.include_router(protocol_users_router)
app.include_router(pinned_items_router)
app.include_router(protocol_folders_router)
app.include_router(workflow_router)

if config.APP_ENV != "production":
    app.include_router(dev_fixtures_router)

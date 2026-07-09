import logging
import logging.config
import uuid
from contextvars import ContextVar
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import ORJSONResponse

# from rich.logging import RichHandler
from sqlalchemy.exc import SQLAlchemyError

from app.config import config
from app.libs.protocol_agent import close_protocol_engine_pool

from .airalogy_api import router as airalogy_router
from .airalogy_files import router as airalogy_files_router
from .aira_imports import router as aira_imports_router
from .answers import router as answers_router
from .attachments import router as attachments_router
from .chats import router as chats_router
from .editor import router as editor_router
from .groups import router as groups_router
from .hub import router as hub_router
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

Path("log").mkdir(exist_ok=True)

app = FastAPI(default_response_class=ORJSONResponse, root_path=config.API_ROOT_PATH)

# 使用 ContextVar 来在请求的生命周期中传递 request_id
request_id_var = ContextVar("request_id", default=None)


# 自定义一个 Filter，为所有日志记录添加 request_id
class RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = request_id_var.get()
        return True


LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id_filter": {
            "()": RequestIdFilter,
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
            "level": "INFO",
            "filters": ["request_id_filter"],
            "rich_tracebacks": True,  # 开启漂亮的 Traceback
            "tracebacks_show_locals": True,  # Traceback 中显示局部变量
        },
        # 文件处理器，将日志写入文件
        "file": {
            "class": "logging.FileHandler",
            "formatter": "file_formatter",
            "filename": "log/app.log",  # 日志文件名
            "level": "INFO",
            "filters": ["request_id_filter"],
        },
    },
    "loggers": {
        # uvicorn 访问日志
        "uvicorn.access": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        # uvicorn 错误日志
        "uvicorn.error": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        # sqlalchemy 引擎日志
        "sqlalchemy.engine": {
            "handlers": ["console", "file"],
            "level": "INFO",  # 设置为 INFO 来捕获 SQL 语句
            "propagate": False,
        },
        # 应用自身的日志
        "app": {
            "handlers": ["console", "file"],
            "level": "INFO",
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
    body = ""
    if request.headers.get("content-type") == "application/json":
        request_body = await request.body()
        body = request_body.decode("utf-8")

    log = f"{request.method} {request['path']}"
    if request.query_params != "":
        log += f" query: {request.query_params}"
    if body != "":
        log += f" body: {body}"
    logger.info(log)
    response = await call_next(request)
    return response


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
    logger.error(f"SQLAlchemyError: {exc}")
    return ORJSONResponse(status_code=400, content={"detail": repr(exc)})


@app.on_event("shutdown")
async def shutdown_protocol_engine_pool():
    await close_protocol_engine_pool()


app.include_router(login_router)
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

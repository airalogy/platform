import os
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException

from app.config import config
from app.models.chat import Chat


MASTERBRAIN_MODEL_NAME_MAP = {
    "qwen-flash": "qwen3.5-flash",
    "qwen-plus": "qwen3.5-plus",
    "qwen-max": "qwen3-max",
    "qwen3-max": "qwen3-max",
}

_MASTERBRAIN_APP: FastAPI | None = None


def _sync_masterbrain_env() -> None:
    env_values = {
        "DASHSCOPE_API_KEY": config.DASHSCOPE_API_KEY,
        "DASHSCOPE_BASE_URL": config.DASHSCOPE_BASE_URL,
        "OPENAI_API_KEY": config.OPENAI_API_KEY,
        "OPENAI_BASE_URL": config.OPENAI_BASE_URL,
    }

    for key, value in env_values.items():
        if value:
            os.environ.setdefault(key, value)


def _get_masterbrain_app() -> FastAPI:
    global _MASTERBRAIN_APP

    if _MASTERBRAIN_APP is None:
        _sync_masterbrain_env()
        from masterbrain.fastapi.main import app as masterbrain_app

        _MASTERBRAIN_APP = masterbrain_app

    return _MASTERBRAIN_APP


def _use_external_masterbrain_api() -> bool:
    return (
        config.MASTERBRAIN_CALL_MODE.strip().lower() == "external"
        and bool(config.CHAT_API_ENDPOINT.strip())
    )


def _masterbrain_request_target(path: str) -> str:
    normalized_path = path.lstrip("/")
    if _use_external_masterbrain_api():
        return f"{config.CHAT_API_ENDPOINT.rstrip('/')}/api/{normalized_path}"
    return f"/api/{normalized_path}"


@asynccontextmanager
async def _masterbrain_client() -> AsyncIterator[httpx.AsyncClient]:
    if _use_external_masterbrain_api():
        async with httpx.AsyncClient() as client:
            yield client
        return

    transport = httpx.ASGITransport(app=_get_masterbrain_app())
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://masterbrain.local",
    ) as client:
        yield client


def _chat_api_error(response: httpx.Response) -> HTTPException:
    detail: object = "Chat API error"
    try:
        response_body = response.json()
        if isinstance(response_body, dict):
            response_detail = response_body.get("detail")
            if response_detail:
                detail = response_detail
    except ValueError:
        if response.text:
            detail = response.text

    return HTTPException(status_code=response.status_code, detail=detail)


async def stream_request(path, json_body, *, method="POST"):
    # print("~~~~~~~~stream chat request params:")
    # print(json.dumps(json, ensure_ascii=False))

    request_target = _masterbrain_request_target(path)
    async with _masterbrain_client() as client:
        async with client.stream(
            method,
            request_target,
            json=json_body,
            timeout=300.0,
        ) as response:
            if response.status_code != 200:
                print(response)
                raise _chat_api_error(response)

            async for chunk in response.aiter_text():
                yield chunk


async def json_request(path, json_body, *, method="POST", timeout=60.0):
    # print("~~~~~~~~json request params:")
    # print(json.dumps(json_body, ensure_ascii=False))
    request_target = _masterbrain_request_target(path)
    async with _masterbrain_client() as client:
        response = await client.request(
            method,
            request_target,
            json=json_body,
            timeout=timeout,
        )
        if response.status_code != 200:
            print(response)
            print(response.text)
            raise _chat_api_error(response)
        return response.json()


def remove_think_from_message(message: dict) -> dict:
    # remove <think> body </think> body from content
    pattern = re.compile(r"<think>.*?</think>", re.DOTALL)
    if message["role"] == "assistant" and message["content"].startswith("<think>"):
        content = pattern.sub("", message["content"])
        return {"role": message["role"], "content": content}
    else:
        return message


def build_masterbrain_model(model: dict) -> dict:
    return {
        "name": MASTERBRAIN_MODEL_NAME_MAP.get(model.get("name"), model.get("name")),
        "enable_thinking": model.get("enable_thinking", False),
        "enable_search": model.get("enable_search", False),
    }


async def chat_qa_language(chat: Chat):
    # qa chat
    async for chunk in stream_request(
        "endpoints/chat/qa/language",
        {
            "model": build_masterbrain_model(chat.model),
            "messages": [remove_think_from_message(msg) for msg in chat.messages],
        },
    ):
        yield chunk


async def hub_chat(chat: Chat):
    async for chunk in stream_request(
        "endpoints/chat/qa/language",
        {
            "model": build_masterbrain_model(chat.model),
            "messages": [remove_think_from_message(msg) for msg in chat.messages],
        },
    ):
        yield chunk


async def field_input_chat(chat: Chat):
    response = await json_request(
        "endpoints/chat/field_input",
        {
            "chat_id": chat.airalogy_id,
            "user_id": str(chat.user_id),
            "model": {"name": chat.model["name"]},
            "history": chat.messages,
            "scenario": {"protocol_schema": chat.context["protocol_schema"]},
            "image_mode": "two_step",
        },
    )
    return response


async def stt(audio_base64: str):
    response = await json_request(
        "endpoints/chat/qa/stt",
        {
            "audio": audio_base64,
            "input_type": "base64",
            "audio_format": "wav",
            "model": "qwen3-asr-flash",
        },
    )
    return response


async def image_vision(
    image_urls: list[str],
    model: Literal[
        "qwen3-vl-flash", "qwen3-vl-plus", "qwen3-vl-max"
    ] = "qwen3-vl-flash",
):
    content = [{"type": "text", "text": "What do you see in this image?"}]
    for image_url in image_urls:
        content.append({"type": "image_url", "image_url": {"url": image_url}})
    response = await json_request(
        "endpoints/chat/qa/vision",
        {
            "chat_id": "chat_id",
            "user_id": "user",
            "model": model,
            "history": [
                {
                    "role": "user",
                    "content": content,
                }
            ],
            "scenario": {},
        },
    )
    return response


async def protocol_generate_aimd(chat: Chat):
    async for chunk in stream_request(
        "endpoints/protocol_generation/aimd",
        {
            "use_model": build_masterbrain_model(chat.model),
            "instruction": chat.context["instruction"],
        },
    ):
        yield chunk


async def protocol_generate_model(chat: Chat):
    async for chunk in stream_request(
        "endpoints/protocol_generation/model",
        {
            "use_model": build_masterbrain_model(chat.model),
            "protocol_aimd": chat.context["protocol_aimd"],
        },
    ):
        yield chunk


async def protocol_generate_assigner(chat: Chat):
    async for chunk in stream_request(
        "endpoints/protocol_generation/assigner",
        {
            "use_model": build_masterbrain_model(chat.model),
            "protocol_aimd": chat.context["protocol_aimd"],
            "protocol_model": chat.context["protocol_model"],
        },
    ):
        yield chunk


async def protocol_check(
    chat: Chat,
):
    async for chunk in stream_request(
        "endpoints/protocol_check",
        {
            "model": build_masterbrain_model(chat.model),
            "feedback": chat.context["feedback"],
            "target_file": chat.context["target_file"],
            "check_num": chat.context["check_num"],
            "aimd_protocol": chat.context["aimd_protocol"],
            "py_model": chat.context["py_model"],
            "py_assigner": chat.context["py_assigner"],
        },
    ):
        yield chunk


async def protocol_debug(chat: Chat):
    response = await json_request(
        "endpoints/protocol_debug",
        {
            "model": build_masterbrain_model(chat.model),
            "full_protocol": chat.context["full_protocol"],
            "suspect_protocol": chat.context["suspect_protocol"],
        },
    )
    return response


async def protocol_code_edit(payload: dict):
    request_payload = {
        **payload,
        "model": build_masterbrain_model(payload["model"]),
    }
    response = await json_request(
        "endpoints/code_edit",
        request_payload,
        timeout=300.0,
    )
    return response


def build_masterbrain_aira_model(model_name: str | None) -> str:
    model = (model_name or config.CHAT_MODEL_FAST or "qwen3.5-flash").strip()
    return MASTERBRAIN_MODEL_NAME_MAP.get(model, model)


async def aira_workflow_step(workflow_data: dict, model_name: str | None = None):
    response = await json_request(
        "endpoints/aira",
        {
            "model": build_masterbrain_aira_model(model_name),
            "workflow_data": workflow_data,
        },
        timeout=300.0,
    )
    return response

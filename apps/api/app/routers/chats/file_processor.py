import os
import uuid
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from masterbrain.usage import UsageContext

from app.database import DBSession
from app.libs.file_storage import download_file
from app.libs.masterbrain import image_vision
from app.models.attachment import Attachment
from app.models.chat import ChatFile

from .utils import generate_tool_call_messages

# Maximum tokens for text content (roughly 1 token = 4 characters)
MAX_TEXT_TOKENS = 8000
CHARS_PER_TOKEN = 4


def trim_content(content: str, max_tokens: int = MAX_TEXT_TOKENS) -> tuple[str, bool]:
    """
    Trim content to stay within token limits.

    Args:
        content: The text content to trim
        max_tokens: Maximum number of tokens allowed

    Returns:
        tuple: (trimmed_content, was_trimmed)
    """
    max_chars = max_tokens * CHARS_PER_TOKEN

    if len(content) <= max_chars:
        return content, False

    # Truncate and add notice
    trimmed = content[:max_chars]
    truncation_notice = (
        "\n\n[NOTE: Content was truncated due to length. "
        f"Original length: {len(content)} chars, "
        f"Trimmed to: {max_chars} chars (~{max_tokens} tokens)]"
    )

    return trimmed + truncation_notice, True


async def _process_text_file(attachment: Attachment) -> str:
    """
    Process a plain text file.

    Args:
        attachment: The attachment object

    Returns:
        str: The text content
    """
    # Download file to /tmp
    tmp_file_path = f"/tmp/{uuid.uuid4()}_{attachment.filename}"
    await download_file(attachment.object_key, tmp_file_path)

    try:
        # Read the downloaded file
        with open(tmp_file_path, "r", encoding="utf-8") as f:
            content = f.read()

        trimmed_content, was_trimmed = trim_content(content)
        return trimmed_content
    except UnicodeDecodeError:
        print(f"File {attachment.filename} is not a text file, skipping")
        return ""
    finally:
        # Clean up temporary file
        if os.path.exists(tmp_file_path):
            os.unlink(tmp_file_path)


async def _process_document_file(attachment: Attachment, file_type: str) -> str:
    """
    Process a PDF or DOCX file using markitdown.

    Args:
        attachment: The attachment object
        file_type: The file type ("pdf" or "docx")

    Returns:
        str: The converted markdown content
    """
    from markitdown import MarkItDown

    # Download file to /tmp with appropriate extension
    tmp_file_path = f"/tmp/{uuid.uuid4()}_{attachment.filename}"
    await download_file(attachment.object_key, tmp_file_path)

    try:
        # Convert using markitdown
        md = MarkItDown()
        result = md.convert(tmp_file_path)
        content = result.text_content

        # Trim if necessary
        trimmed_content, was_trimmed = trim_content(content)
        return trimmed_content
    finally:
        # Clean up temporary file
        if os.path.exists(tmp_file_path):
            os.unlink(tmp_file_path)


async def _process_image_files(
    file_urls: list[str], *, usage_context: UsageContext | None = None
) -> str:
    """
    Process image files using the image_vision function.

    Args:
        file_urls: List of image URLs

    Returns:
        str: The vision processing result
    """
    image_vision_result = await image_vision(
        file_urls, usage_context=usage_context
    )
    return image_vision_result["history"][-1]["content"]


async def process_files(
    db_session: DBSession,
    files: list[ChatFile],
    user_id: UUID,
    *,
    usage_context: UsageContext | None = None,
) -> list[dict[str, Any]]:
    """
    Process uploaded files and return tool call messages.

    This function handles multiple file types:
    - Images: Processed using image_vision
    - PDFs: Converted to text using markitdown
    - DOCX: Converted to text using markitdown
    - Text files: Read directly

    Large text content is automatically trimmed to avoid exceeding LLM context limits.

    Args:
        db_session: Database session
        files: List of file objects from the user message
        user_id: Current user's ID

    Returns:
        list: Tool call messages to be added to chat history

    Raises:
        HTTPException: If file is not found or user doesn't have permission
    """
    if not files or len(files) == 0:
        return []

    # Separate files by type
    image_files = []
    text_files = []
    pdf_files = []
    docx_files = []

    for file in files:
        # Verify file exists and user has permission
        attachment = await Attachment.find_by(
            db_session,
            [Attachment.id == file.id, Attachment.user_id == user_id],
        )
        if attachment is None:
            raise HTTPException(
                status_code=400, detail=f"File not found, id: {file.id}"
            )

        # Categorize by type
        if file.type == "image":
            image_files.append((file, attachment))
        elif file.type == "text":
            text_files.append((file, attachment))
        elif file.type == "pdf":
            pdf_files.append((file, attachment))
        elif file.type == "docx":
            docx_files.append((file, attachment))
        else:
            raise HTTPException(
                status_code=400, detail=f"File type: {file.type} not supported"
            )

    tool_call_messages = []

    # Process images together (they can be batch processed)
    if image_files:
        file_urls = [await attachment.url() for _, attachment in image_files]
        image_content = await _process_image_files(
            file_urls, usage_context=usage_context
        )

        messages = generate_tool_call_messages(
            function_name="processing_user_uploaded_image_file",
            function_args={"images": [file.model_dump() for file, _ in image_files]},
            function_result={"images_content": image_content},
        )
        tool_call_messages.extend(messages)

    # Process text files
    for file, attachment in text_files:
        text_content = await _process_text_file(attachment)

        messages = generate_tool_call_messages(
            function_name="processing_user_uploaded_text_file",
            function_args={"file": file.model_dump()},
            function_result={"file_content": text_content},
        )
        tool_call_messages.extend(messages)

    # Process PDF files
    for file, attachment in pdf_files:
        pdf_content = await _process_document_file(attachment, "pdf")

        messages = generate_tool_call_messages(
            function_name="processing_user_uploaded_pdf_file",
            function_args={"file": file.model_dump()},
            function_result={"file_content": pdf_content},
        )
        tool_call_messages.extend(messages)

    # Process DOCX files
    for file, attachment in docx_files:
        docx_content = await _process_document_file(attachment, "docx")

        messages = generate_tool_call_messages(
            function_name="processing_user_uploaded_docx_file",
            function_args={"file": file.model_dump()},
            function_result={"file_content": docx_content},
        )
        tool_call_messages.extend(messages)

    return tool_call_messages

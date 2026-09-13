import contextlib
import io
import logging
import warnings

from masterbrain.usage import UsageContext
from semantic_text_splitter import TextSplitter

from app.config import config
from app.libs.embedding_config import EMBEDDING_BATCH_SIZE

logger = logging.getLogger("app")

chunk_splitter = TextSplitter.from_tiktoken_model(
    "gpt-3.5-turbo", capacity=300, overlap=20
)

word_splitter = None
stopwords = None


def load_cutter_class():
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r".*invalid escape sequence.*",
            category=SyntaxWarning,
            module=r"cutword(\..*)?",
        )
        output_buffer = io.StringIO()
        with (
            contextlib.redirect_stdout(output_buffer),
            contextlib.redirect_stderr(output_buffer),
        ):
            from cutword import Cutter

    return Cutter


# lazy load stopwords
def get_stopwords() -> set[str]:
    global stopwords
    if stopwords is None:
        stopwords = set()
        with open("app/libs/stopwords.txt", "r", encoding="utf-8") as f:
            for line in f:
                stopword = line.strip()
                if stopword:
                    stopwords.add(stopword)
    return stopwords


# lazy load word splitter
def get_word_splitter():
    global word_splitter
    if word_splitter is None:
        Cutter = load_cutter_class()
        word_splitter = Cutter(want_long_word=True)
    return word_splitter


def remove_stopwords(words: list[str]) -> list[str]:
    return [word for word in words if word.strip() not in get_stopwords()]


def text_to_chunks(text: str) -> list[str]:
    return chunk_splitter.chunks(text)


def text_to_words(text: str, exclude_stopword: bool = True) -> list[str]:
    words = get_word_splitter().cutword(text)
    if exclude_stopword:
        words = remove_stopwords(words)
    return words


async def create_embeddings(
    texts: list[str], *, usage_context: UsageContext | None = None
) -> list[list[float]]:
    # Lazy import avoids a cycle through model registration and usage persistence.
    from app.libs.masterbrain import text_embeddings

    return await text_embeddings(texts, usage_context=usage_context)


async def text_to_vectors(
    texts: list[str], *, usage_context: UsageContext | None = None
) -> list[list[float]]:
    res = []
    for i in range(0, len(texts), EMBEDDING_BATCH_SIZE):
        res.extend(
            await create_embeddings(
                texts[i : i + EMBEDDING_BATCH_SIZE], usage_context=usage_context
            )
        )
    return res


async def optional_text_to_vectors(
    texts: list[str], *, usage_context: UsageContext | None = None
) -> list[list[float]] | None:
    if not config.effective_embeddings_enabled:
        return None
    try:
        return await text_to_vectors(texts, usage_context=usage_context)
    except Exception as exc:  # noqa: BLE001 - optional provider boundary; never catches cancellation
        # Only the optional model boundary is degraded, never database errors.
        # Do not log raw provider responses, credentials, or research text.
        logger.warning(
            "Embedding unavailable; using keyword search/index (%s)", type(exc).__name__
        )
        return None


async def text_to_embeddings(
    text: str, *, usage_context: UsageContext | None = None
) -> list[tuple[str, list[str], list[float] | None]]:
    chunks = text_to_chunks(text)
    vectors = await optional_text_to_vectors(chunks, usage_context=usage_context)
    return [
        (chunk, text_to_words(chunk), vectors[i] if vectors is not None else None)
        for i, chunk in enumerate(chunks)
    ]

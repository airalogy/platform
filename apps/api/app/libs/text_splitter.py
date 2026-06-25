import contextlib
import io
import os
import warnings

from openai import OpenAI
from semantic_text_splitter import TextSplitter

from app.config import config

qwen_client = OpenAI(
    api_key=config.DASHSCOPE_API_KEY,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

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
        with contextlib.redirect_stdout(output_buffer), contextlib.redirect_stderr(
            output_buffer
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


def create_embeddings(texts: list[str]) -> list[list[float]]:
    if len(texts) > 6:
        raise ValueError("文本数量不能大于6")
    res = qwen_client.embeddings.create(
        model="text-embedding-v4",
        input=texts,
        dimensions=1024,
        encoding_format="float",
    )
    return [embedding.embedding for embedding in res.data]


def text_to_vectors(texts: list[str]) -> list[list[float]]:
    if len(texts) > 6:
        # 如果文本数量大于6，则分批处理
        res = []
        for i in range(0, len(texts), 6):
            res.extend(create_embeddings(texts[i : i + 6]))
    else:
        res = create_embeddings(texts)
    return res


def text_to_embeddings(text: str) -> list[tuple[str, list[str], list[float]]]:
    chunks = text_to_chunks(text)
    vectors = text_to_vectors(chunks)
    return [(chunk, text_to_words(chunk), vectors[i]) for i, chunk in enumerate(chunks)]

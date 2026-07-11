import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class TextChunk:
    """
    尚未写入数据库的文本分块。
    """
    chunk_index: int
    page_no: Optional[int]
    content: str

    @property
    def char_count(self) -> int:
        return len(self.content)


def clean_chunk_text(text: str) -> str:
    """
    清理分块内部的多余空白，同时保留段落结构。
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def split_text_by_page(
    raw_text: str
) -> list[tuple[Optional[int], str]]:
    """
    根据解析阶段生成的“[第x页]”标记切分页码。

    PDF、PPTX 通常带页码标记；
    DOCX、TXT、Markdown 没有页码时整体作为一段处理。
    """

    page_pattern = re.compile(r"\[第(\d+)页\]\s*")
    matches = list(page_pattern.finditer(raw_text))

    if not matches:
        return [(None, clean_chunk_text(raw_text))]

    page_sections: list[tuple[Optional[int], str]] = []

    for index, match in enumerate(matches):
        page_no = int(match.group(1))
        content_start = match.end()

        if index + 1 < len(matches):
            content_end = matches[index + 1].start()
        else:
            content_end = len(raw_text)

        page_content = clean_chunk_text(
            raw_text[content_start:content_end]
        )

        if page_content:
            page_sections.append(
                (page_no, page_content)
            )

    return page_sections


def find_best_break_position(
    text: str,
    start: int,
    expected_end: int
) -> int:
    """
    尽量在句号、换行等自然边界处切分。

    如果找不到合适边界，就按固定长度切分。
    """

    search_start = start + (expected_end - start) // 2

    break_characters = (
        "\n",
        "。",
        "！",
        "？",
        "；",
        "!",
        "?",
        ";",
        "，",
        ",",
    )

    best_position = -1

    for character in break_characters:
        position = text.rfind(
            character,
            search_start,
            expected_end
        )

        if position > best_position:
            best_position = position

    if best_position == -1:
        return expected_end

    # 将标点包含在当前分块中
    return best_position + 1


def split_section_into_chunks(
    text: str,
    *,
    chunk_size: int = 800,
    chunk_overlap: int = 120
) -> list[str]:
    """
    将一页或一段正文切分为多个片段。

    chunk_size：
        每个分块目标长度，默认 800 个字符。

    chunk_overlap：
        相邻分块重叠长度，默认 120 个字符。
        重叠内容能够减少知识点刚好被切断的问题。
    """

    if chunk_size <= 0:
        raise ValueError("chunk_size 必须大于 0")

    if chunk_overlap < 0:
        raise ValueError("chunk_overlap 不能小于 0")

    if chunk_overlap >= chunk_size:
        raise ValueError(
            "chunk_overlap 必须小于 chunk_size"
        )

    text = clean_chunk_text(text)

    if not text:
        return []

    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    text_length = len(text)

    while start < text_length:
        expected_end = min(
            start + chunk_size,
            text_length
        )

        if expected_end < text_length:
            end = find_best_break_position(
                text=text,
                start=start,
                expected_end=expected_end
            )
        else:
            end = expected_end

        chunk = clean_chunk_text(text[start:end])

        if chunk:
            chunks.append(chunk)

        if end >= text_length:
            break

        next_start = end - chunk_overlap

        # 防止极端情况下无法向前推进
        if next_start <= start:
            next_start = end

        start = next_start

    return chunks


def build_material_chunks(
    raw_text: str,
    *,
    chunk_size: int = 800,
    chunk_overlap: int = 120
) -> list[TextChunk]:
    """
    将资料全文转换为带页码和序号的分块列表。
    """

    if not raw_text or not raw_text.strip():
        return []

    page_sections = split_text_by_page(raw_text)

    result: list[TextChunk] = []
    chunk_index = 0

    for page_no, page_text in page_sections:
        page_chunks = split_section_into_chunks(
            page_text,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )

        for content in page_chunks:
            result.append(
                TextChunk(
                    chunk_index=chunk_index,
                    page_no=page_no,
                    content=content
                )
            )

            chunk_index += 1

    return result
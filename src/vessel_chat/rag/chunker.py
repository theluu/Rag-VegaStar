"""Tách tài liệu Markdown thành đoạn theo tiêu đề `##`, giới hạn độ dài mỗi đoạn."""

import hashlib
import re
from dataclasses import dataclass

DEFAULT_SECTION = "Tổng quan"


@dataclass(frozen=True)
class Chunk:
    source: str
    title: str
    section: str
    ordinal: int
    content: str

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(f"{self.source}\x00{self.section}\x00{self.ordinal}\x00{self.content}".encode()).hexdigest()

    @property
    def embed_text(self) -> str:
        return f"{self.title} › {self.section}\n{self.content}"


def _split_long(paragraph: str, max_chars: int) -> list[str]:
    if len(paragraph) <= max_chars:
        return [paragraph]
    sentences = re.split(r"(?<=[.!?;:])\s+", paragraph)
    parts, current = [], ""
    for sentence in sentences:
        while len(sentence) > max_chars:  # câu quá dài: cắt cứng tại khoảng trắng
            cut = sentence.rfind(" ", 0, max_chars) or max_chars
            parts.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if current and len(current) + 1 + len(sentence) > max_chars:
            parts.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        parts.append(current)
    return parts


def _pack(section_text: str, max_chars: int) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", section_text) if p.strip()]
    pieces = [piece for p in paragraphs for piece in _split_long(p, max_chars)]
    chunks, current = [], ""
    for piece in pieces:
        if current and len(current) + 2 + len(piece) > max_chars:
            chunks.append(current)
            current = piece
        else:
            current = f"{current}\n\n{piece}" if current else piece
    if current:
        chunks.append(current)
    return chunks


def chunk_markdown(source: str, text: str, max_chars: int) -> list[Chunk]:
    title = source
    sections: list[tuple[str, list[str]]] = [(DEFAULT_SECTION, [])]
    for line in text.splitlines():
        if line.startswith("# ") and title == source:
            title = line[2:].strip()
        elif line.startswith("## "):
            sections.append((line[3:].strip(), []))
        else:
            sections[-1][1].append(line)

    chunks: list[Chunk] = []
    for section, lines in sections:
        for i, content in enumerate(_pack("\n".join(lines), max_chars)):
            chunks.append(Chunk(source, title, section, i, content))
    return chunks

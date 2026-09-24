"""EmbeddingGemma token counts from the local Ollama GGUF vocabulary.

The Hugging Face tokenizer is gated. This reader uses the sentencepiece
vocabulary already downloaded with the Ollama model and a unigram search.
It does not add BOS or EOS. Ollama's embed request adds those separately.
"""

from __future__ import annotations

import json
import os
import struct
from pathlib import Path

# Content digest of the embeddinggemma GGUF checked in preflight. The file
# lives under the local Ollama models directory, which differs per machine.
MODEL_DIGEST = "sha256:0800cbac9c2064dde519420e75e512a83cb360de3ad5df176185dc69652fc515"
MODEL_MEDIA_TYPE = "application/vnd.ollama.image.model"


def ollama_models_dir() -> Path:
    override = os.environ.get("OLLAMA_MODELS")
    if override:
        return Path(override)
    return Path.home() / ".ollama" / "models"


def embeddinggemma_blob(models_dir: Path | None = None) -> Path:
    """Return the local embeddinggemma GGUF blob for this machine.

    Prefers the model layer recorded in the Ollama manifest so a teammate's
    pull is used when it differs from the pinned digest.
    """
    root = models_dir or ollama_models_dir()
    digest = MODEL_DIGEST
    manifest = (
        root
        / "manifests"
        / "registry.ollama.ai"
        / "library"
        / "embeddinggemma"
        / "latest"
    )
    if manifest.is_file():
        data = json.loads(manifest.read_text())
        for layer in data.get("layers", []):
            if layer.get("mediaType") == MODEL_MEDIA_TYPE and layer.get("digest"):
                digest = layer["digest"]
                break
    return root / "blobs" / digest.replace(":", "-")


BLOB = embeddinggemma_blob()
SCALAR = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}


def load_tokenizer(path: Path = BLOB) -> tuple[list[str], list[float], list[int]]:
    with path.open("rb") as handle:
        magic, _version = struct.unpack("<4sI", handle.read(8))
        if magic != b"GGUF":
            raise ValueError(f"{path} is not a GGUF file")
        _tensors, kv_count = struct.unpack("<QQ", handle.read(16))
        tokens: list[str] | None = None
        scores: list[float] | None = None
        types: list[int] | None = None
        for _ in range(kv_count):
            key = _read_string(handle)
            value_type = struct.unpack("<I", handle.read(4))[0]
            if value_type == 8:
                _read_string(handle)
            elif value_type == 9:
                element_type = struct.unpack("<I", handle.read(4))[0]
                count = struct.unpack("<Q", handle.read(8))[0]
                if key == "tokenizer.ggml.tokens":
                    tokens = [_read_string(handle) for _ in range(count)]
                elif key == "tokenizer.ggml.scores":
                    scores = list(struct.unpack("<" + "f" * count, handle.read(4 * count)))
                elif key == "tokenizer.ggml.token_type":
                    types = list(struct.unpack("<" + "i" * count, handle.read(4 * count)))
                elif element_type == 8:
                    for _ in range(count):
                        _read_string(handle)
                else:
                    handle.seek(SCALAR[element_type] * count, 1)
            else:
                handle.seek(SCALAR[value_type], 1)
    if tokens is None or scores is None or types is None:
        raise ValueError("GGUF blob is missing tokenizer arrays")
    return tokens, scores, types


class GemmaTokenizer:
    """SentencePiece merge tokenizer over the local EmbeddingGemma vocabulary.

    Counts policy text only. Ollama's embed call also adds BOS and EOS.
    """

    name = "embeddinggemma-gguf-spm-v1"

    def __init__(self, path: Path = BLOB) -> None:
        tokens, scores, types = load_tokenizer(path)
        self.token_id: dict[str, int] = {}
        self.token_score: dict[str, float] = {}
        self.byte_token = [-1] * 256
        self.byte_text = [""] * 256
        for index, token in enumerate(tokens):
            if types[index] == 6 and token.startswith("<0x") and token.endswith(">"):
                value = int(token[3:-1], 16)
                self.byte_token[value] = index
                self.byte_text[value] = token
            if types[index] in (1, 4, 6):
                self.token_id[token] = index
                self.token_score[token] = scores[index]
        if any(value < 0 for value in self.byte_token):
            raise ValueError("EmbeddingGemma vocabulary is missing byte fallback tokens")

    def count(self, text: str) -> int:
        if not text or not text.strip():
            return 0
        return len(self.encode(text))

    def encode(self, text: str) -> list[int]:
        converted = text.replace(" ", "▁")
        symbols: list[str] = []
        for char in converted:
            if char in self.token_id:
                symbols.append(char)
                continue
            for byte in char.encode("utf-8"):
                symbols.append(self.byte_text[byte])
        while len(symbols) > 1:
            best_index = -1
            best_score = float("-inf")
            for index in range(len(symbols) - 1):
                merged = symbols[index] + symbols[index + 1]
                score = self.token_score.get(merged)
                if score is not None and score > best_score:
                    best_score = score
                    best_index = index
            if best_index < 0:
                break
            symbols[best_index : best_index + 2] = [symbols[best_index] + symbols[best_index + 1]]
        return [self.token_id[symbol] for symbol in symbols]


def _read_string(handle) -> str:
    size = struct.unpack("<Q", handle.read(8))[0]
    return handle.read(size).decode("utf-8", "replace")


if __name__ == "__main__":
    tokens, scores, types = load_tokenizer()
    from collections import Counter

    print("tokens", len(tokens), Counter(types))
    for word in ("the", "▁the", "▁", "kg", "▁kg", ".", "23"):
        print(word, tokens.index(word) if word in tokens else "MISSING")
    print("sample", [(i, repr(tokens[i]), types[i]) for i in (100, 1000, 5000)])

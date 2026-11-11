"""Lossless UTF-8-safe token windows: 500–1000 tokens, exact 10% overlap.

Counts and offsets refer to the cl100k_base tokenization of the entire document.
The final window is rebalanced; only documents shorter than 500 remain short.
"""
import hashlib
from functools import lru_cache


@lru_cache(maxsize=1)
def encoding():
    import tiktoken
    return tiktoken.get_encoding('cl100k_base')


def chunk_text(text, target=800):
    if not 500 <= target <= 1000 or target % 10:
        raise ValueError('Parça hedefi 500–1000 arasında, 10’un katı olmalı.')
    if not text.strip():
        return []
    enc = encoding()
    tokens = enc.encode(text, disallowed_special=())
    data = text.encode('utf-8')
    offsets = [0]
    for token in tokens:
        offsets.append(offsets[-1] + len(enc.decode_single_token_bytes(token)))
    def boundary(pos):
        offset = offsets[pos]
        return offset == len(data) or data[offset] & 0xC0 != 0x80
    chunks, start, previous_end = [], 0, 0
    while start < len(tokens):
        remaining = len(tokens) - start
        if remaining <= 1000:
            end, following = len(tokens), len(tokens)
        else:
            candidates = sorted(range(500, 1001, 10), key=lambda n: (abs(n-target), n))
            for size in candidates:
                end = start + size
                following = end - size // 10
                if len(tokens) - following >= 500 and boundary(end) and boundary(following):
                    break
            else:
                raise ValueError('UTF-8 sınırlarında %10 örtüşmeli parça üretilemedi.')
        content = data[offsets[start]:offsets[end]].decode('utf-8')
        chunks.append({'ordinal': len(chunks), 'text': content,
                       'token_start': start, 'token_end': end, 'token_count': end-start,
                       'byte_start': offsets[start], 'byte_end': offsets[end],
                       'overlap_from_previous': max(0, previous_end-start),
                       'short_document': len(tokens) < 500,
                       'tokenizer': 'cl100k_base', 'sha256': hashlib.sha256(content.encode()).hexdigest()})
        previous_end, start = end, following
    return chunks

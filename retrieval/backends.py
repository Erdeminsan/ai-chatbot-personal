"""Local models; no remote inference and no lexical fallback."""
import os
from functools import lru_cache
import numpy as np


class RetrievalError(Exception):
    pass


def unit_vectors(values):
    values = np.asarray(values, dtype=np.float32)
    if values.ndim != 2 or not np.isfinite(values).all():
        raise RetrievalError('Geçersiz embedding matrisi.')
    norms = np.linalg.norm(values, axis=1, keepdims=True)
    if (norms <= 0).any():
        raise RetrievalError('Sıfır embedding vektörü.')
    return values / norms


def windows(text, tokenizer, budget):
    """Character boundaries, measured with the actual model tokenizer.

    Each source character is represented. Model-specific windows are separate
    from persisted 500–1000 cl100k document chunks.
    """
    if budget < 16:
        raise RetrievalError('Model bağlam bütçesi çok küçük.')
    start = 0
    while start < len(text):
        tail = text[start:]
        if len(tokenizer.encode(tail, add_special_tokens=False)) <= budget:
            yield tail
            break
        lo, hi = 1, len(tail)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if len(tokenizer.encode(tail[:mid], add_special_tokens=False)) <= budget:
                lo = mid
            else:
                hi = mid - 1
        yield tail[:lo]
        start += max(1, lo - lo // 10)


class LocalEmbedder:
    def __init__(self):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise RetrievalError('Önce pip install -r requirements-rag.txt çalıştırın.') from None
        self.name = os.environ.get('EMBEDDING_MODEL', 'intfloat/multilingual-e5-small')
        self.revision = os.environ.get('EMBEDDING_REVISION') or None
        self.offline = os.environ.get('RAG_OFFLINE') == '1'
        self.model = SentenceTransformer(self.name, revision=self.revision, trust_remote_code=False,
                                        local_files_only=self.offline, device=os.environ.get('RAG_DEVICE', 'cpu'))
        resolved = getattr(self.model[0].auto_model.config, '_commit_hash', None) or self.revision or 'local'
        self.signature = f'{self.name}@{resolved}:e5-prefix-window-mean-v1'
        self.budget = min(int(self.model.max_seq_length), 512)

    def encode(self, texts, query=False):
        prefix = 'query: ' if query else 'passage: '
        token = self.model.tokenizer
        overhead = len(token.encode(prefix, add_special_tokens=True)) + 8
        flattened, groups = [], []
        for text in texts:
            parts = list(windows(text, token, self.budget - overhead))
            if not parts:
                raise RetrievalError('Boş metin embedding yapılamaz.')
            groups.append((len(flattened), len(parts)))
            flattened.extend(prefix + part for part in parts)
        if any(len(token.encode(part, add_special_tokens=True)) > self.budget for part in flattened):
            raise RetrievalError('Embedding bağlam sınırı aşıldı; metin kesilmedi.')
        vectors = self.model.encode(flattened, batch_size=16, normalize_embeddings=True, show_progress_bar=False)
        return unit_vectors([np.asarray(vectors[start:start+count]).mean(axis=0) for start, count in groups])


class LocalReranker:
    def __init__(self):
        try:
            from sentence_transformers import CrossEncoder
            from torch.nn import Identity
        except ImportError:
            raise RetrievalError('Önce pip install -r requirements-rag.txt çalıştırın.') from None
        self.name = os.environ.get('RERANK_MODEL', 'BAAI/bge-reranker-v2-m3')
        self.model = CrossEncoder(self.name, max_length=512, activation_fn=Identity(),
                                  revision=os.environ.get('RERANK_REVISION') or None,
                                  local_files_only=os.environ.get('RAG_OFFLINE') == '1',
                                  trust_remote_code=False, device=os.environ.get('RAG_DEVICE', 'cpu'))

    def score(self, query, documents):
        token = self.model.tokenizer
        query_len = len(token.encode(query, add_special_tokens=False))
        if query_len > 128:
            raise RetrievalError('Sorguyu kısaltın: reranker en fazla 128 model tokenı kabul ediyor.')
        budget = 512 - query_len - token.num_special_tokens_to_add(pair=True) - 8
        pairs, groups = [], []
        for document in documents:
            parts = list(windows(document, token, budget))
            groups.append((len(pairs), len(parts)))
            pairs.extend((query, part) for part in parts)
        for question, passage in pairs:
            if len(token(question, passage, add_special_tokens=True, truncation=False)['input_ids']) > 512:
                raise RetrievalError('Reranker bağlam sınırı aşıldı; metin kesilmedi.')
        scores = np.asarray(self.model.predict(pairs, batch_size=8, show_progress_bar=False)).reshape(-1)
        if len(scores) != len(pairs) or not np.isfinite(scores).all():
            raise RetrievalError('Reranker geçersiz skor üretti.')
        # All windows are scored; keep the strongest matching window per chunk.
        return [float(scores[start:start+count].max()) for start, count in groups]


@lru_cache(maxsize=1)
def embedder():
    return LocalEmbedder()


@lru_cache(maxsize=1)
def reranker():
    return LocalReranker()

"""Atomic local cosine index for normalized web/Confluence exports."""
import hashlib
import json
import os
import sqlite3
import tempfile
from pathlib import Path
from urllib.parse import urlsplit
import numpy as np
from .backends import RetrievalError, unit_vectors
from .chunking import chunk_text


def read_documents(source):
    source = Path(source).resolve()
    files = [source] if source.is_file() else sorted(source.rglob('normalized.json'))
    latest = {}
    for file in files:
        data = json.loads(file.read_text(encoding='utf-8'))
        if not isinstance(data.get('markdown'), str) or not data['markdown'].strip():
            continue
        url = data.get('source_url') or data.get('url') or data.get('requested_url')
        if not url:
            raise RetrievalError(f'Kaynak URL eksik: {file.name}')
        source_type = data.get('source_type', 'confluence')
        key = (source_type, data.get('source_base_url', ''), str(data.get('page_id') or url))
        # Most recent page version; web duplicates use exported timestamp.
        rank = (int(data.get('version') or 0), data.get('exported_at', ''), str(file))
        if key not in latest or rank > latest[key][0]:
            latest[key] = (rank, data, file)
    for key, (_, data, file) in sorted(latest.items()):
        yield {'document_id': hashlib.sha256(repr(key).encode()).hexdigest(),
               'title': data.get('title', ''), 'source_url': data.get('source_url') or data.get('url') or data.get('requested_url'),
               'source_type': data.get('source_type', 'confluence'), 'version': data.get('version'),
               'source_file': str(file), 'warnings': data.get('warnings', []),
               'generated_content_requires_review': data.get('generated_content_requires_review', False),
               'acl_status': data.get('acl_status', 'not_collected'), 'media_groups': data.get('media_groups', []), 'markdown': data['markdown']}


def build_index(source, target, model, chunk_size=800):
    target = Path(target).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.index-', suffix='.sqlite3', dir=target.parent)
    os.close(fd)
    documents, count = 0, 0
    connection = sqlite3.connect(temporary)
    try:
        connection.executescript('CREATE TABLE metadata (key TEXT PRIMARY KEY,value TEXT); CREATE TABLE chunks (id TEXT PRIMARY KEY,payload TEXT NOT NULL,vector BLOB NOT NULL);')
        dimension = None
        for document in read_documents(source):
            markdown = document.pop('markdown')
            groups = document.pop('media_groups')
            spans = []
            for group in groups:
                text = group.get('markdown', '')
                pos = markdown.find(text) if text else -1
                if pos >= 0:
                    begin = len(markdown[:pos].encode('utf-8'))
                    spans.append((begin, begin + len(text.encode('utf-8')), group.get('id')))
            parts = chunk_text(markdown, target=chunk_size)
            for part in parts:
                part['media_group_ids'] = [ident for begin, end, ident in spans
                                           if begin < part['byte_end'] and end > part['byte_start']]
            for offset in range(0, len(parts), 32):
                batch = parts[offset:offset+32]
                vectors = unit_vectors(model.encode([part['text'] for part in batch]))
                if len(vectors) != len(batch):
                    raise RetrievalError('Embedding sayısı uyuşmuyor.')
                if dimension is not None and dimension != vectors.shape[1]:
                    raise RetrievalError('Embedding boyutu değişti.')
                dimension = vectors.shape[1]
                for part, vector in zip(batch, vectors):
                    ident = f"{document['document_id']}:{part['ordinal']}"
                    payload = {**document, **part, 'id': ident}
                    connection.execute('INSERT INTO chunks VALUES (?,?,?)',
                                       (ident, json.dumps(payload, ensure_ascii=False), vector.astype('<f4').tobytes()))
                    count += 1
            documents += 1
        if not count:
            raise RetrievalError('İndekslenecek normalized.json içeriği bulunamadı; mevcut indeks korundu.')
        metadata = {'schema_version': 1, 'embedding_signature': model.signature, 'dimension': dimension,
                    'documents': documents, 'chunks': count, 'chunk_target': chunk_size,
                    'tokenizer': 'cl100k_base', 'overlap_ratio': 0.1}
        connection.executemany('INSERT INTO metadata VALUES (?,?)', [(k, json.dumps(v)) for k, v in metadata.items()])
        connection.commit()
        connection.close()
        os.replace(temporary, target)
        return metadata
    finally:
        connection.close()
        Path(temporary).unlink(missing_ok=True)


def search_index(path, query, embedding, reranking, k=20, limit=5):
    query = query.strip()
    if not query or len(query) > 2000:
        raise RetrievalError('Sorgu 1–2000 karakter olmalı.')
    if not 1 <= limit <= k <= 100:
        raise RetrievalError('1 ≤ sonuç sayısı ≤ K ≤ 100 olmalı.')
    path = Path(path).resolve()
    if not path.is_file():
        raise RetrievalError('Önce index_exports komutuyla indeks oluşturun.')
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
        meta = {key: json.loads(value) for key, value in db.execute('SELECT key,value FROM metadata')}
        if meta['embedding_signature'] != embedding.signature:
            raise RetrievalError('Embedding modeli değişti; indeksi yeniden oluşturun.')
        query_vector = unit_vectors(embedding.encode([query], query=True))[0]
        if len(query_vector) != meta['dimension']:
            raise RetrievalError('Sorgu embedding boyutu indeksle uyuşmuyor.')
        candidates = []
        cursor = db.execute('SELECT id,payload,vector FROM chunks ORDER BY id')
        # Bound working memory while performing exact cosine retrieval.
        while rows := cursor.fetchmany(256):
            matrix = np.stack([np.frombuffer(row[2], dtype='<f4') for row in rows])
            scores = matrix @ query_vector
            for row, score in zip(rows, scores):
                candidates.append((float(score), row[0], row[1]))
            candidates.sort(key=lambda row: (-row[0], row[1]))
            candidates = candidates[:k]
    selected = []
    for rank, (score, _, payload) in enumerate(candidates, 1):
        selected.append({**json.loads(payload), 'vector_score': score, 'vector_rank': rank})
    if not selected:
        return []
    # A separate pair model scores only the vector top-K, never the entire corpus.
    scores = np.asarray(reranking.score(query, [row['text'] for row in selected])).reshape(-1)
    if len(scores) != len(selected) or not np.isfinite(scores).all():
        raise RetrievalError('Reranker sonuç sayısı veya skorları geçersiz; sıralama yapılmadı.')
    for row, score in zip(selected, scores):
        row['rerank_score'] = float(score)
        row['source_link'] = row['source_url'] if urlsplit(row['source_url']).scheme in {'http', 'https'} else ''
    selected.sort(key=lambda row: (-row['rerank_score'], row['vector_rank']))
    for rank, row in enumerate(selected, 1):
        row['rerank_rank'] = rank
    return selected[:limit]

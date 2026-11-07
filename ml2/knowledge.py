"""Small lexical retrieval over explicit, versioned broker excerpts only."""
from collections import Counter
from datetime import date
import math
import re
from .contracts import array, read_json, require, text


def tokens(value):
    return re.findall(r'[^\W_]{2,}', value.casefold(), re.UNICODE)


class KnowledgeBase:
    def __init__(self, raw=None):
        raw = raw if raw is not None else {'version': 'none', 'documents': []}
        require(isinstance(raw, dict), 'knowledge: expected object')
        self.version = text(raw.get('version'), 'knowledge.version')
        self.documents = array(raw.get('documents'), 'knowledge.documents', 10000, False)
        ids = set()
        for doc in self.documents:
            require(isinstance(doc, dict), 'knowledge document: expected object')
            for field in ('id', 'title', 'source', 'version', 'text'):
                text(doc.get(field), f'knowledge.{field}', 4000)
            require(doc['id'] not in ids, 'Duplicate knowledge ID')
            ids.add(doc['id'])
            require(isinstance(doc.get('tags', []), list) and all(isinstance(t, str) for t in doc.get('tags', [])), 'Invalid tags')
            for field in ('valid_from', 'valid_until'):
                if doc.get(field):
                    date.fromisoformat(doc[field])
            if doc.get('valid_from') and doc.get('valid_until'):
                require(doc['valid_from'] <= doc['valid_until'], 'Invalid knowledge validity interval')
        self.raw = raw

    @classmethod
    def load(cls, path):
        return cls(read_json(path)) if path else cls()

    def retrieve(self, dialog, as_of=None, k=4, max_chars=6500):
        if as_of:
            date.fromisoformat(as_of)
        docs = [d for d in self.documents if
                (not d.get('valid_from') and not d.get('valid_until')) or
                (as_of and (not d.get('valid_from') or d['valid_from'] <= as_of) and
                 (not d.get('valid_until') or as_of <= d['valid_until']))]
        bags = [Counter(tokens(d['text'] + ' ' + d['title'] + ' ' + ' '.join(d.get('tags', [])))) for d in docs]
        query = set(tokens(' '.join(m['text'] for m in dialog['messages'] if m['speaker'] in ('client', 'operator'))))
        avg = sum(sum(b.values()) for b in bags) / max(1, len(bags))
        ranks = []
        for d, b in zip(docs, bags):
            value = 0
            for token in query & b.keys():
                df = sum(token in other for other in bags)
                idf = math.log(1 + (len(bags) - df + .5) / (df + .5))
                value += idf * b[token] * 2.2 / (b[token] + 1.2 * (.25 + .75 * sum(b.values()) / max(avg, 1)))
            if value:
                ranks.append((value, d))
        selected, used = [], 0
        for _, doc in sorted(ranks, key=lambda pair: (-pair[0], pair[1]['id'])):
            if len(selected) >= k:
                break
            if used + len(doc['text']) <= max_chars:
                selected.append(doc)
                used += len(doc['text'])
        return selected

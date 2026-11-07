"""One-call evaluator with one bounded structure repair; pure local input/output contract."""
from pathlib import Path
import time
from .contracts import (ContractError, canonical, digest, loads, rubric, conversation,
                        response_schema, validate_results)
from .knowledge import KnowledgeBase
from .provider import ModelError
from .scoring import summarize
from .decoding import schema_for, decode

SYSTEM = (Path(__file__).parent / 'prompts/system.txt').read_text()
PROMPT_VERSION = 'ml2-cqa-5'


class EvaluationFailure(RuntimeError):
    def __init__(self, message, attempts):
        super().__init__(message)
        self.attempts = attempts


class Evaluator:
    def __init__(self, provider, checklist, knowledge=None, as_of=None):
        self.provider = provider
        self.checklist = rubric(checklist)
        self.knowledge = knowledge or KnowledgeBase()
        self.as_of = as_of

    def evaluate(self, raw):
        started = time.monotonic()
        dialog = conversation(raw)
        excerpts = self.knowledge.retrieve(dialog, self.as_of)
        schema = schema_for(self.checklist, dialog, excerpts)
        prompt_rubric = {**self.checklist, 'criteria': [
            {k: v for k, v in c.items() if k not in ('section', 'title')}
            for c in self.checklist['criteria']]}
        task = {'rubric': prompt_rubric, 'conversation': dialog,
                'knowledge_excerpts': excerpts, 'knowledge_as_of': self.as_of}
        messages = [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': canonical(task)}]
        attempts = []
        for index in range(2):
            try:
                response, usage = self.provider.complete(messages, schema)
            except ModelError as exc:
                attempts.append({'attempt': index + 1, 'error': str(exc)})
                raise EvaluationFailure(str(exc), attempts) from exc
            try:
                results = validate_results(decode(loads(response), self.checklist), self.checklist, dialog, excerpts)
            except (ContractError, TypeError) as exc:
                reason = str(exc) if isinstance(exc, ContractError) else 'Wrong field types'
                attempts.append({'attempt': index + 1, 'usage': usage, 'validation_error': reason})
                if index == 1:
                    raise EvaluationFailure('Invalid assessment after one repair: ' + reason, attempts) from exc
                # Re-evaluate original task; don't echo untrusted generated instructions into a repair prompt.
                messages.append({'role': 'user', 'content': 'Validation error: ' + reason +
                                 '. Reassess all criteria; return the full corrected object.'})
                continue
            attempts.append({'attempt': index + 1, 'usage': usage})
            return {'conversation_id': dialog['conversation_id'], 'language': dialog['language'],
                    'channel': dialog['channel'], 'status': 'ok', 'results': results,
                    'summary': summarize(results, self.checklist),
                    'provenance': {'conversation_hash': digest(dialog), 'rubric_hash': digest(self.checklist),
                        'rubric_version': self.checklist['version'], 'prompt_version': PROMPT_VERSION,
                        'prompt_hash': digest(SYSTEM), 'knowledge_hash': digest(self.knowledge.raw),
                        'knowledge_version': self.knowledge.version, 'knowledge_as_of': self.as_of,
                        'retrieved_ids': [d['id'] for d in excerpts], 'attempts': attempts,
                        'elapsed_seconds': round(time.monotonic() - started, 3)}}

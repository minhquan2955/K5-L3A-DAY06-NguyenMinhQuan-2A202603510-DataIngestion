"""Conservative automatic evidence metrics, separate from human audit scores."""
from collections import defaultdict
from typing import Any

from .ingestion import canonical_text


def evaluate_query(question: dict[str, Any], hits: list[dict[str, Any]],
                   *, strategy: str | None = None) -> dict[str, Any]:
    """A hit needs the gold document/page and a complete normalized evidence quote."""
    golds = [question] + question.get('alternative_gold', [])
    checked_hits = []
    for hit in hits[:3]:
        metadata = hit.get('metadata', {})
        document_id = hit.get('document_id', metadata.get('document_id'))
        page = hit.get('page', metadata.get('page'))
        text = canonical_text(hit['text'])
        matched = any(document_id == gold['gold_source_id'] and page == gold['gold_page']
                      and bool(canonical_text(gold['evidence_quote']))
                      and canonical_text(gold['evidence_quote']) in text for gold in golds)
        checked_hits.append({**hit, 'evidence_hit': matched})
    return {
        'strategy': strategy, 'question_id': question['id'], 'split': question['split'],
        'question': question['question'], 'expected_answer': question.get('expected_answer'),
        'gold': [{key: gold[key] for key in ('gold_source_id', 'gold_page', 'evidence_quote')}
                 for gold in golds],
        'requested_filter': question.get('filter', {}), 'hits': checked_hits,
        'hit_at_1': int(bool(checked_hits and checked_hits[0]['evidence_hit'])),
        'hit_at_3': int(any(hit['evidence_hit'] for hit in checked_hits)),
        'match_method': 'normalized_substring_with_document_and_page',
        'manual_grounding_score': None,
    }


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Keep explicit numerators/denominators for each strategy and split."""
    groups = defaultdict(list)
    seen = set()
    for trace in traces:
        identity = (trace['strategy'], trace['split'], trace['question_id'])
        if identity in seen:
            raise ValueError(f'Duplicate evaluation trace: {identity}')
        seen.add(identity)
        groups[identity[:2]].append(trace)
    result = []
    for (strategy, split), rows in sorted(groups.items()):
        row = {'strategy': strategy, 'split': split, 'n_questions': len(rows)}
        for metric in ('hit_at_1', 'hit_at_3'):
            count = sum(int(trace[metric]) for trace in rows)
            row[metric] = {'hits': count, 'total': len(rows), 'rate': count / len(rows)}
        result.append(row)
    return {'by_strategy_split': result}

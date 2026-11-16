"""Conservative candidate recall for literal, affirmative curriculum relationship sentences.

This does not infer relationships from co-occurrence or similarity. Whole-clause
matching prevents negation, quoted counterexamples and substring endpoints from
being mistaken for positive assertions. Ambiguous names remain for model review.
"""
from collections import defaultdict
import re


def explicit_relations(entities, chunks):
    names = defaultdict(list)
    for entity in entities:
        names[entity.name.strip()].append(entity.entity_id)
    unique = {name: ids[0] for name, ids in names.items() if len(ids) == 1}
    if len(unique) < 2:
        return []
    alternatives = '|'.join(re.escape(n) for n in sorted(unique, key=lambda n: (-len(n), n)))
    a, b = f'(?P<a>{alternatives})', f'(?P<b>{alternatives})'
    patterns = [
        (re.compile(f'(?:在(?:本课程|该课程|本章|本节)的学习顺序中[，,])?学习{b}(?:之前|前)[，,]?(?:需要|必须|应当|应)?先(?:掌握|学习|理解|了解){a}'), 'PREREQUISITE', False),
        (re.compile(f'{a}是{b}的(?:先修知识|前置知识|前提|基础)'), 'PREREQUISITE', False),
        (re.compile(f'{b}(?:包含|包括){a}'), 'CONTAINS', True),
        (re.compile(f'{a}是{b}的(?:一种|一类)'), 'CONTAINS', True),
        (re.compile(f'{a}是{b}的(?:一个|一种|典型|具体)?(?:例子|示例|应用实例)'), 'EXAMPLE_OF', False),
    ]
    result = []
    for chunk in chunks:
        if '```' in chunk.text:
            continue
        for sentence in re.finditer(r'[^。！？!?；;\n]+[。！？!?；;]?', chunk.text):
            evidence = sentence.group().strip()
            if not evidence or len(evidence) > 500 or evidence.endswith(('？', '?')):
                continue
            separator = chunk.text.rfind('\n\n', 0, sentence.start())
            paragraph_start = separator + 2 if separator >= 0 else 0
            paragraph_end = chunk.text.find('\n\n', sentence.end())
            paragraph = chunk.text[paragraph_start:
                                   paragraph_end if paragraph_end >= 0 else len(chunk.text)]
            if re.search(r'错误|反例|假设|如果|假如|若|不成立|不正确|不对|判断题|是否|并非|不是|无需|不需要|[“”「」『』"`]', paragraph):
                continue
            clause = evidence.rstrip('。！？!?；;').strip()
            clause = re.sub(r'^(?:[-*•]|\d+[.)、])\s+', '', clause)
            for pattern, kind, reverse in patterns:
                match = pattern.fullmatch(clause)
                if match is None:
                    continue
                left, right = unique[match['a']], unique[match['b']]
                if left != right:
                    result.append(dict(from_id=right if reverse else left,
                        to_id=left if reverse else right, type=kind, evidence=evidence,
                        confidence=None, chunk_id=chunk.identity.chunk_id,
                        evidence_start=sentence.start() + len(sentence.group()) - len(sentence.group().lstrip())))
                break
            hierarchy = re.fullmatch(f'{b}(?:的知识体系)?(?:包含|包括)(?P<children>(?:{alternatives})(?:[、和及](?:{alternatives}))*)', clause)
            if hierarchy:
                for token in re.finditer(alternatives, hierarchy['children']):
                    name = token.group()
                    if hierarchy['b'] == name:
                        continue
                    result.append(dict(from_id=unique[hierarchy['b']], to_id=unique[name],
                        type='CONTAINS', evidence=evidence, confidence=None,
                        chunk_id=chunk.identity.chunk_id,
                        evidence_start=sentence.start() + len(sentence.group()) - len(sentence.group().lstrip())))
    return result[:128]

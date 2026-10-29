#!/usr/bin/env python3
"""Build the reviewed 2024-2026 objective-question catalog from PDF transcriptions.

The importer is intentionally offline. Callers first fetch the six pinned PDFs,
the pinned management-paper transcription, and the English HTML transcription
used to correct PDF text extraction. This script then produces deterministic
JSON that is reviewed and served without runtime network access.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


YEARS = (2024, 2025, 2026)
ENGLISH_SECTIONS = ('cloze', 'text1', 'text2', 'text3', 'text4', 'partb')
ANSWER_LABELS = 'ABCDEFGH'
# Corrections verified against a second PDF copy when the pinned transcription
# contains a duplicate or visibly corrupted option.
MANAGEMENT_OPTION_CORRECTIONS = {
    (2025, 40, 'A'): '乙和丁支持丙。',
}


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def _english_payload(path: Path) -> dict:
    html = path.read_text(encoding='utf-8')
    chunks = [
        json.loads(match.group(1))
        for match in re.finditer(
            r'self\.__next_f\.push\(\[1,("(?:\\.|[^"\\])*")\]\)</script>',
            html,
        )
    ]
    stream = '\n'.join(chunks)
    marker = stream.index('"questions"')
    decoder = json.JSONDecoder()
    for start in (index for index in range(marker - 1, -1, -1) if stream[index] == '{'):
        try:
            value, length = decoder.raw_decode(stream[start:])
        except json.JSONDecodeError:
            continue
        if start + length > marker and isinstance(value, dict) and 'questions' in value:
            return value
    raise ValueError(f'No question payload in {path}')


def _passage(payload: dict) -> str:
    paragraphs = []
    for paragraph in payload['paragraphs']:
        paragraphs.append(' '.join(sentence['text'] for sentence in paragraph['sentences']))
    return '\n\n'.join(paragraphs)


def _english_questions(root: Path, year: int) -> list[dict]:
    result = []
    for section in ENGLISH_SECTIONS:
        payload = _english_payload(root / f'{year}-{section}.html')
        passage = _passage(payload)
        if section == 'cloze':
            passage = re.sub(r'\{\{(\d+)\}\}', r'____\1____', passage)
        shared_options = payload.get('sharedOptions', [])
        for question in payload['questions']:
            number = int(question['number'])
            options = question.get('options') or shared_options
            options = sorted(options, key=lambda option: option['label'])
            labels = [option['label'] for option in options]
            answer_label = question['answer']
            if answer_label not in labels:
                raise ValueError(f'{year} English question {number} has no answer option')
            if section == 'cloze':
                prompt = f'{passage}\n\n第 {number} 空请选择最合适的选项。'
                topic = '真题 · 完形填空'
            elif section == 'partb':
                prompt = f'{passage}\n\n第 {number} 题请选择最合适的小标题。'
                topic = '真题 · 新题型'
            else:
                stem = question['stem']['text']
                prompt = f'{passage}\n\n{number}. {stem}'
                topic = f'真题 · 阅读理解 Text {section[-1]}'
            correct = question.get('analysis', {}).get('correct', {}).get('explanation')
            answer_text = options[labels.index(answer_label)]['text']
            explanation = correct or (
                f'参考答案为 {answer_label}（{answer_text}）。'
                '本题为标题匹配题，请把选项主旨与相应段落逐句核对。'
            )
            result.append({
                'id': f'real-{year}-204-{number:03}',
                'version': 1,
                'subject': '英语',
                'topic': topic,
                'prompt': prompt,
                'options': [option['text'] for option in options],
                'answer': labels.index(answer_label),
                'explanation': explanation,
                'source': f'{year} 年英语（二）真题 · PDF 题面与公开参考答案交叉校对',
                'difficulty': '历年真题',
                'paper_year': year,
                'paper_subject': '204',
                'question_number': number,
                'image_path': None,
            })
    result.sort(key=lambda question: question['question_number'])
    return result


def _management_questions(root: Path, year: int) -> list[dict]:
    paper_path = root / '199管综真题_Markdown题库' / f'{year}年' / f'{year}年199真题_chunks.jsonl'
    answer_path = root / '199管综答案_Markdown题库' / f'{year}年' / f'{year}年199真题解析_chunks.jsonl'
    paper = {row['question_no']: row for row in _read_jsonl(paper_path) if row['question_no'] <= 55}
    answer_rows = [row for row in _read_jsonl(answer_path) if row['question_no'] <= 55]
    answers: dict[int, dict] = {}
    for row in answer_rows:
        current = answers.setdefault(row['question_no'], {'answer': row['answer'], 'explanations': []})
        if current['answer'] != row['answer']:
            raise ValueError(f'{year} management answer conflict for {row["question_no"]}')
        if row.get('explanation'):
            current['explanations'].append(row['explanation'])
    result = []
    for number in range(1, 56):
        question = paper[number]
        answer = answers[number]
        options = dict(question['options'])
        for label in options:
            options[label] = MANAGEMENT_OPTION_CORRECTIONS.get((year, number, label), options[label])
        labels = sorted(options)
        answer_label = answer['answer']
        source_suffix = '；2026 解析含第三方推演' if year == 2026 else ''
        result.append({
            'id': f'real-{year}-199-{number:03}',
            'version': 1,
            'subject': '数学' if number <= 25 else '逻辑',
            'topic': f'真题 · {question["category"]}',
            'prompt': question['stem'],
            'options': [options[label] for label in labels],
            'answer': labels.index(answer_label),
            'explanation': '\n\n'.join(answer['explanations']) or f'参考答案为 {answer_label}。',
            'source': f'{year} 年 199 管综真题 · PDF 题面与参考答案交叉校对{source_suffix}',
            'difficulty': '历年真题',
            'paper_year': year,
            'paper_subject': '199',
            'question_number': number,
            'image_path': f'/exam-papers/{year}/199/q{number:02}.webp',
        })
    return result


def build(english_root: Path, management_root: Path) -> dict:
    questions = []
    for year in YEARS:
        questions.extend(_management_questions(management_root, year))
        questions.extend(_english_questions(english_root, year))
    questions.sort(key=lambda question: (question['paper_year'], question['paper_subject'], question['question_number']))
    if len(questions) != 300 or len({question['id'] for question in questions}) != 300:
        raise ValueError('Expected exactly 300 unique objective questions')
    for year in YEARS:
        yearly = [question for question in questions if question['paper_year'] == year]
        if len(yearly) != 100:
            raise ValueError(f'Expected 100 objective questions for {year}')
    return {'catalog_version': 'real-papers-2024-2026-v1', 'questions': questions}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--english-html-root', type=Path, required=True)
    parser.add_argument('--management-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    content = json.dumps(build(args.english_html_root, args.management_root), ensure_ascii=False, indent=2) + '\n'
    args.output.write_text(content, encoding='utf-8')


if __name__ == '__main__':
    main()

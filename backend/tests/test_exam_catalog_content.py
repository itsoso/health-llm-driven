"""Content invariants: preserve saved question identities and audit new arithmetic."""
import json
import re
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / 'backend/app/data/exam_questions.json'
REAL_CATALOG = ROOT / 'backend/app/data/exam_real_questions.json'
REAL_SOURCES = ROOT / 'backend/app/data/exam_real_sources.json'


def test_catalog_preserves_legacy_prompts_options_and_grades():
    questions = json.loads(CATALOG.read_text())['questions']
    by_id = {q['id']: q for q in questions}
    sources = [ROOT / 'mobile/utils/examStudy.ts', ROOT / 'mobile/utils/examQuestionBank.ts']
    matched = 0
    for source in sources:
        for line in source.read_text().splitlines():
            m = re.search(r"\{id:'([^']+)',subject:'([^']+)',topic:'([^']+)',prompt:'((?:[^'\\]|\\.)*)',options:\[(.*?)\],answer:(\d+),explanation:'((?:[^'\\]|\\.)*)'", line)
            if m is None:
                continue
            identity, subject, topic, prompt, options, answer, explanation = m.groups()
            decode = lambda value: value.replace("\\'", "'").replace('\\n', '\n').replace('\\\\', '\\')
            q = by_id[identity]
            assert (q['subject'], q['topic'], q['prompt'], q['answer'], q['explanation']) == (subject, topic, decode(prompt), int(answer), decode(explanation))
            assert q['options'] == [decode(value) for value in re.findall(r"'((?:[^'\\]|\\.)*)'", options)]
            matched += 1
    assert matched == 80, 'legacy extraction must cover every existing saved identity'
    assert len(questions) == len(by_id) and len(questions) > matched


def test_reviewed_catalog_has_complete_unique_choices_and_honest_provenance():
    questions = json.loads(CATALOG.read_text())['questions']
    for q in questions:
        assert len(q['options']) == len(set(q['options']))
        assert 0 <= q['answer'] < len(q['options'])
        assert q['version'] >= 1 and q['explanation'] and q['prompt']
        assert q['source'].startswith('原创')
    variants = [q for q in questions if q['id'].startswith('m3')]
    assert variants and all('参数变式' in q['source'] for q in variants)


def test_math_content_checked_against_independent_expected_results():
    by_id = {q['id']: q for q in json.loads(CATALOG.read_text())['questions']}
    # First member of each of the twenty arithmetic families, independently reviewed.
    expected = {
        'm300': '99元', 'm303': '80', 'm306': '12/5天', 'm309': '40千米/时',
        'm312': '8人', 'm315': '15种', 'm318': '20种', 'm321': '1/7',
        'm324': '3/4', 'm327': '100元', 'm330': '30元', 'm333': '155',
        'm336': '62', 'm339': '14厘米', 'm342': '54平方厘米', 'm345': '13',
        'm348': '200/7千克', 'm351': '8', 'm354': '121元', 'm357': '15',
    }
    for identity, result in expected.items():
        q = by_id[identity]
        assert q['options'][q['answer']] == result
    # All nonreplacement sampling variants must stay in [0,1].
    for identity in ('m321', 'm322', 'm323', 'm324', 'm325', 'm326'):
        q = by_id[identity]
        assert all(0 <= Fraction(option) <= 1 for option in q['options'])


def test_cost_argument_asks_about_total_cost_not_only_labor():
    q = next(q for q in json.loads(CATALOG.read_text())['questions'] if q['id'] == 'l213')
    assert '降低总成本' in q['prompt']
    assert '总成本低于' in q['options'][q['answer']]


def test_real_paper_catalog_covers_every_objective_question_with_provenance():
    catalog = json.loads(REAL_CATALOG.read_text())
    questions = catalog['questions']
    assert catalog['catalog_version'] == 'real-papers-2024-2026-v1'
    assert len(questions) == 300
    assert len({q['id'] for q in questions}) == 300
    for year in (2024, 2025, 2026):
        yearly = [q for q in questions if q['paper_year'] == year]
        assert len(yearly) == 100
        management = [q for q in yearly if q['paper_subject'] == '199']
        english = [q for q in yearly if q['paper_subject'] == '204']
        assert [q['question_number'] for q in management] == list(range(1, 56))
        assert [q['question_number'] for q in english] == list(range(1, 46))
        assert all(q['image_path'] == f'/exam-papers/{year}/199/q{q["question_number"]:02}.webp'
                   for q in management)
        assert all(q.get('image_path') is None for q in english)
    for q in questions:
        assert q['version'] == 1
        assert q['difficulty'] == '历年真题'
        assert 0 <= q['answer'] < len(q['options'])
        assert len(q['options']) == len(set(q['options']))
        assert q['prompt'] and q['explanation'] and '真题' in q['source']


def test_real_paper_sources_are_pinned_and_management_images_exist():
    sources = json.loads(REAL_SOURCES.read_text())
    assert sources['structured_management_revision'] == '3bcabc9647772c73868c03b86532aa194087d0e4'
    assert len(sources['papers']) == 6
    assert all(re.fullmatch(r'[0-9a-f]{64}', paper['sha256']) for paper in sources['papers'])
    questions = json.loads(REAL_CATALOG.read_text())['questions']
    for q in questions:
        if q['paper_subject'] == '199':
            assert (ROOT / 'frontend/public' / q['image_path'].removeprefix('/')).is_file()

import { sortIntegrityIssues, type IntegrityIssue } from '../dataHealth';

function issue(code: string, severity: string): IntegrityIssue {
  return { code, severity, detail: code, count: 1, fix_hint: '' };
}

describe('sortIntegrityIssues', () => {
  it('orders critical before warning before info', () => {
    const sorted = sortIntegrityIssues([
      issue('a', 'info'),
      issue('b', 'critical'),
      issue('c', 'warning'),
    ]);
    expect(sorted.map((i) => i.severity)).toEqual(['critical', 'warning', 'info']);
  });

  it('pushes unknown severities to the end', () => {
    const sorted = sortIntegrityIssues([issue('x', 'mystery'), issue('y', 'critical')]);
    expect(sorted.map((i) => i.code)).toEqual(['y', 'x']);
  });

  it('does not mutate the input array', () => {
    const input = [issue('a', 'info'), issue('b', 'critical')];
    sortIntegrityIssues(input);
    expect(input.map((i) => i.code)).toEqual(['a', 'b']);
  });
});

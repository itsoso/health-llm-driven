import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { SafeActionCardContent } from '../ActionCardPanel';


describe('SafeActionCardContent', () => {
  it('does not create executable elements from stored markdown HTML', () => {
    const { container } = render(
      <SafeActionCardContent
        content={'<img src=x onerror="alert(1)">\n<script>alert(2)</script>\n**正常建议**'}
      />,
    );

    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('script')).toBeNull();
    expect(container.textContent).toContain('正常建议');
  });

  it('does not expose javascript links', () => {
    const { container } = render(
      <SafeActionCardContent content={'[危险链接](javascript:alert(1))'} />,
    );

    const link = container.querySelector('a');
    expect(link?.getAttribute('href') || '').not.toMatch(/^javascript:/i);
  });

  it('renders markdown tables without interpreting cell HTML', () => {
    const { container } = render(
      <SafeActionCardContent
        content={'| 指标 | 数值 |\n| --- | --- |\n| HRV | <img src=x onerror=alert(1)> |'}
      />,
    );

    expect(container.querySelector('table')).not.toBeNull();
    expect(container.querySelector('img')).toBeNull();
    expect(container.textContent).toContain('HRV');
  });
});

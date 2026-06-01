import React from 'react';
import { render } from '@testing-library/react-native';
import { Text, View } from 'react-native';
import EvidenceChip from '../EvidenceChip';
import { semanticColors } from '../../../constants/theme';

// light mode (默认)
jest.mock('react-native/Libraries/Utilities/useColorScheme', () => ({
  __esModule: true,
  default: () => 'light',
}));

function bgOf(tree: ReturnType<typeof render>) {
  const view = tree.UNSAFE_getByType(View);
  return (StyleArray(view.props.style) as any).backgroundColor;
}
function fgOf(tree: ReturnType<typeof render>) {
  const text = tree.UNSAFE_getByType(Text);
  return (StyleArray(text.props.style) as any).color;
}
// 合并 style 数组成单对象
function StyleArray(style: any): Record<string, unknown> {
  return Array.isArray(style) ? Object.assign({}, ...style.filter(Boolean)) : style || {};
}

describe('EvidenceChip', () => {
  it('renders nothing for missing or unknown level', () => {
    expect(render(<EvidenceChip level={null} />).toJSON()).toBeNull();
    expect(render(<EvidenceChip level="bogus" />).toJSON()).toBeNull();
  });

  it('maps high → success tone', () => {
    const t = render(<EvidenceChip level="high" />);
    expect(t.getByText('强证据')).toBeTruthy();
    expect(bgOf(t)).toBe(semanticColors.success.bg);
    expect(fgOf(t)).toBe(semanticColors.success.fg);
  });

  it('maps medical_grade → danger tone', () => {
    const t = render(<EvidenceChip level="medical_grade" />);
    expect(t.getByText('需医生')).toBeTruthy();
    expect(bgOf(t)).toBe(semanticColors.danger.bg);
    expect(fgOf(t)).toBe(semanticColors.danger.fg);
  });

  it('maps medium → warning and low → neutral', () => {
    expect(bgOf(render(<EvidenceChip level="medium" />))).toBe(semanticColors.warning.bg);
    expect(bgOf(render(<EvidenceChip level="low" />))).toBe(semanticColors.neutral.bg);
  });
});

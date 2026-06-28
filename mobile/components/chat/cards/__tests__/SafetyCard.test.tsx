import React from 'react';
import { render } from '@testing-library/react-native';
import { renderCard, renderServerCards } from '../registry';

describe('SafetyCard', () => {
  const descriptor = {
    type: 'safety',
    data: {
      title: '今天不建议高强度训练',
      severity: 'high',
      summary: '睡眠不足且 HRV 明显低于近期基线，建议把训练降级。',
      recommendations: [
        '改为 20 分钟低强度步行或拉伸',
        '训练中如有胸闷、头晕、异常心悸，立即停止',
        '明早根据睡眠和静息心率重新评估',
        '第四条不应展示',
      ],
      boundary: '这不是诊断；如出现急性不适或持续症状，请及时就医。',
      requires_medical_attention: true,
    },
  };

  it('renders safety guidance with conservative language', () => {
    const element = renderCard(descriptor);
    expect(element).not.toBeNull();

    const screen = render(element!);
    expect(screen.getByText('今天不建议高强度训练')).toBeTruthy();
    expect(screen.getByText('高风险')).toBeTruthy();
    expect(screen.getByText('睡眠不足且 HRV 明显低于近期基线，建议把训练降级。')).toBeTruthy();
    expect(screen.getByText('改为 20 分钟低强度步行或拉伸')).toBeTruthy();
    expect(screen.getByText('训练中如有胸闷、头晕、异常心悸，立即停止')).toBeTruthy();
    expect(screen.getByText('明早根据睡眠和静息心率重新评估')).toBeTruthy();
    expect(screen.queryByText('第四条不应展示')).toBeNull();
    expect(screen.getByText(/不是诊断/)).toBeTruthy();
    expect(screen.getByText('需要关注')).toBeTruthy();
  });

  it('accepts backend safety descriptors', () => {
    expect(renderServerCards([descriptor]).map((card) => card.type)).toEqual(['safety']);
  });

  it('does not crash on malformed backend safety data', () => {
    const element = renderCard({
      type: 'safety',
      data: {
        title: 123,
        severity: 'critical',
        summary: { text: 'bad payload' },
        recommendations: '改为低强度活动',
        boundary: 456,
        requires_medical_attention: 'yes',
      },
    } as any);

    expect(element).not.toBeNull();
    expect(() => render(element!)).not.toThrow();
  });
});

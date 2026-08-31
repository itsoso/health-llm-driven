import React from 'react';
import { Alert, Linking } from 'react-native';
import { fireEvent, render, waitFor } from '@testing-library/react-native';

import MedicalCitations from '../MedicalCitations';

describe('MedicalCitations', () => {
  it('keeps sources visible, opens the official link, and shows the medical boundary', async () => {
    const open = jest.spyOn(Linking, 'openURL').mockResolvedValueOnce(undefined as never);
    const screen = render(
      <MedicalCitations
        citations={[
          {
            sourceId: 'nhc:adult-weight-standard',
            title: '中国成人体重判定标准',
            organization: '国家卫生健康委员会',
            url: 'https://www.nhc.gov.cn/example.pdf',
            topic: 'bmi',
            claimScope: 'BMI 公式与中国成人范围。',
          },
        ]}
      />,
    );

    expect(screen.getByText('参考来源')).toBeTruthy();
    expect(screen.getByText('中国成人体重判定标准')).toBeTruthy();
    expect(screen.getByText('国家卫生健康委员会')).toBeTruthy();
    expect(screen.getByText('健康信息用于辅助管理，不替代诊断；做医疗决定前请咨询医生。')).toBeTruthy();

    fireEvent.press(screen.getByLabelText('打开参考来源：中国成人体重判定标准'));
    await waitFor(() => {
      expect(open).toHaveBeenCalledWith('https://www.nhc.gov.cn/example.pdf');
    });
    open.mockRestore();
  });

  it('renders nothing when no safe citation exists', () => {
    const screen = render(<MedicalCitations citations={[]} />);
    expect(screen.toJSON()).toBeNull();
  });

  it('tells the user when an official source cannot be opened', async () => {
    const open = jest.spyOn(Linking, 'openURL').mockRejectedValueOnce(new Error('offline'));
    const alert = jest.spyOn(Alert, 'alert').mockImplementation(() => undefined);
    const screen = render(
      <MedicalCitations
        citations={[{
          sourceId: 'cdc:adult-bmi-categories',
          title: '成人 BMI 计算方法与分类',
          organization: '美国疾病控制与预防中心',
          url: 'https://www.cdc.gov/bmi/adult-calculator/bmi-categories.html',
        }]}
      />,
    );

    fireEvent.press(screen.getByLabelText('打开参考来源：成人 BMI 计算方法与分类'));
    await waitFor(() => {
      expect(alert).toHaveBeenCalledWith(
        '暂时无法打开来源',
        '请检查网络后重试。',
      );
    });
    open.mockRestore();
    alert.mockRestore();
  });
});

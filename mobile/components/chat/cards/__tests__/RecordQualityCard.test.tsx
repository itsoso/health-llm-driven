import React from 'react';
import { act, fireEvent, render, waitFor } from '@testing-library/react-native';

import { RecordQualityCardView } from '../RecordQualityCard';
import { renderCard } from '../registry';
import {
  recalculateDietRecordNutrition,
  updateDietRecord,
} from '../../../../services/diet';

jest.mock('../../../../services/diet', () => ({
  recalculateDietRecordNutrition: jest.fn(),
  updateDietRecord: jest.fn(),
}));

const mockRecalculate = recalculateDietRecordNutrition as jest.MockedFunction<
  typeof recalculateDietRecordNutrition
>;
const mockUpdate = updateDietRecord as jest.MockedFunction<typeof updateDietRecord>;
const originalCryptoDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'crypto');

function installTestCrypto(value: unknown): void {
  Object.defineProperty(globalThis, 'crypto', {
    configurable: true,
    value,
  });
}

function baseAdjustCard(overrides?: Record<string, unknown>) {
  return {
    domain: 'diet',
    title: '午餐已记录',
    summary: '770 kcal · 蛋白 30g',
    metrics: [
      { label: '热量', value: '770kcal' },
      { label: '蛋白', value: '30g' },
    ],
    expanded_sections: ['adjust_record'],
    adjust_record: {
      record_id: 123,
      meal_type: 'snack',
      food_items: '100克葡萄 五十克饼干',
      calories: 230,
      protein: 3,
      carbs: 52,
      fat: 4,
      fiber: 2,
      updated_at: '2026-08-20T12:00:00Z',
    },
    boundary: '健康管理建议，不替代医生诊断或治疗。',
    ...overrides,
  };
}

describe('RecordQualityCard inline diet adjuster', () => {
  let uuidCounter = 0;

  beforeEach(() => {
    jest.clearAllMocks();
    uuidCounter = 0;
    installTestCrypto({
      randomUUID: jest.fn(() => (
        `00000000-0000-4000-8000-${String(++uuidCounter).padStart(12, '0')}`
      )),
    });
  });

  afterAll(() => {
    if (originalCryptoDescriptor) {
      Object.defineProperty(globalThis, 'crypto', originalCryptoDescriptor);
    } else {
      delete (globalThis as { crypto?: unknown }).crypto;
    }
  });

  it('renders a screenshot-ready diet share strip when progress data is available', () => {
    const { getAllByText, getByText } = render(
      <RecordQualityCardView
        {...(baseAdjustCard({
          expanded_sections: [],
          progress: {
            protein_total_g: 37,
            protein_target_g: 112,
            remaining_protein_g: 75,
            calories_total: 1040,
            meals_count: 2,
          },
          next_action: '晚餐优先 40g 蛋白，少油少刺激。',
        }) as any)}
      />,
    );

    expect(getByText('今日摄入')).toBeTruthy();
    expect(getByText('1040 kcal')).toBeTruthy();
    expect(getByText('蛋白进度')).toBeTruthy();
    expect(getAllByText('37/112g').length).toBeGreaterThanOrEqual(1);
    expect(getByText('下一餐')).toBeTruthy();
    expect(getAllByText('晚餐优先 40g 蛋白，少油少刺激。').length).toBeGreaterThanOrEqual(1);
    expect(getByText('#饮食记录 #小巴')).toBeTruthy();
  });

  it('shows seven-day recording consistency without a streak or ranking', () => {
    const { getByText, queryByText } = render(
      <RecordQualityCardView
        {...(baseAdjustCard({
          expanded_sections: [],
          progress: {
            protein_total_g: 37,
            protein_target_g: 112,
            recorded_days_7d: 5,
          },
        }) as any)}
      />,
    );

    expect(getByText('近7天记录 5 天')).toBeTruthy();
    expect(queryByText(/连续|排名|断签/)).toBeNull();
  });

  it('renders measurement-backed weight goal distance and seven-day change', () => {
    const { getByLabelText, getByText } = render(
      <RecordQualityCardView
        {...(baseAdjustCard({
          expanded_sections: [],
          goal_progress: {
            goal_type: 'weight_loss',
            current_kg: 73,
            target_kg: 70,
            remaining_kg: 3,
            baseline_kg: 75,
            progress_pct: 40,
            change_7d_kg: -1,
            measured_on: '2026-07-25',
            freshness: 'fresh',
            status: 'active',
          },
        }) as any)}
      />,
    );

    expect(getByText('距目标 3kg')).toBeTruthy();
    expect(getByText('73 → 70kg')).toBeTruthy();
    expect(getByText('近7天 -1kg')).toBeTruthy();
    expect(getByLabelText('减重目标进度 40%')).toBeTruthy();
  });

  it('labels stale weight data instead of presenting it as current', () => {
    const { getByText, queryByText } = render(
      <RecordQualityCardView
        {...(baseAdjustCard({
          expanded_sections: [],
          goal_progress: {
            goal_type: 'weight_loss',
            current_kg: 76,
            target_kg: 70,
            remaining_kg: 6,
            measured_on: '2026-07-17',
            freshness: 'stale',
            status: 'active',
          },
        }) as any)}
      />,
    );

    expect(getByText('体重数据较旧，更新后再看趋势')).toBeTruthy();
    expect(getByText('测于 7月17日')).toBeTruthy();
    expect(queryByText(/近7天/)).toBeNull();
  });

  it('shows a review boundary for an unsafe target without progress encouragement', () => {
    const { getByText, queryByLabelText } = render(
      <RecordQualityCardView
        {...(baseAdjustCard({
          expanded_sections: [],
          goal_progress: {
            goal_type: 'weight_loss',
            current_kg: 68,
            target_kg: 55,
            freshness: 'fresh',
            status: 'target_requires_review',
          },
        }) as any)}
      />,
    );

    expect(getByText('目标需要复核')).toBeTruthy();
    expect(getByText('当前目标可能不适合直接推进，请先核对身高和目标体重。')).toBeTruthy();
    expect(queryByLabelText(/减重目标进度/)).toBeNull();
  });

  it('hides the weight goal section when no verified goal progress is present', () => {
    const { queryByText } = render(
      <RecordQualityCardView {...(baseAdjustCard({ expanded_sections: [] }) as any)} />,
    );

    expect(queryByText('目标进度')).toBeNull();
    expect(queryByText(/距目标/)).toBeNull();
  });

  it('renders the inline editor seeded from adjust_record when expanded', () => {
    const { getByLabelText, getByTestId, getByText } = render(
      <RecordQualityCardView {...(baseAdjustCard() as any)} onCardDataChange={jest.fn()} />,
    );

    // 编辑器已就地展开, 食物/餐次/营养以初值填充
    expect(getByText('就地修正这条记录，保存后直接更新')).toBeTruthy();
    expect((getByLabelText('食物描述').props as any).value).toBe('100克葡萄 五十克饼干');
    expect((getByLabelText('热量').props as any).value).toBe('230');
    expect((getByLabelText('蛋白').props as any).value).toBe('3');
    expect((getByLabelText('膳食纤维').props as any).value).toBe('2');
    expect(getByText('保存修正')).toBeTruthy();
    expect(getByText('加餐')).toBeTruthy();

    const stopPropagation = jest.fn();
    fireEvent(getByTestId('diet-adjust-inline-editor'), 'touchStart', { stopPropagation });
    expect(stopPropagation).toHaveBeenCalledTimes(1);
  });

  it('does not render the editor without the adjust_record expanded section', () => {
    const { queryByText } = render(
      <RecordQualityCardView
        {...(baseAdjustCard({ expanded_sections: [] }) as any)}
        onCardDataChange={jest.fn()}
      />,
    );
    expect(queryByText('就地修正这条记录，保存后直接更新')).toBeNull();
  });

  it('does not render the editor when record_id is missing', () => {
    const { queryByText } = render(
      <RecordQualityCardView
        {...(baseAdjustCard({ adjust_record: { meal_type: 'snack', food_items: '葡萄' } }) as any)}
        onCardDataChange={jest.fn()}
      />,
    );
    expect(queryByText('就地修正这条记录，保存后直接更新')).toBeNull();
  });

  it('recalculates nutrition exactly once when the food description changes', async () => {
    mockRecalculate.mockResolvedValue({
      id: 123,
      user_id: 1,
      record_date: '2026-07-02',
      meal_type: 'lunch',
      food_items: '两碗虾滑鸡蛋汤',
      calories: 360,
      protein: 32,
      carbs: 16,
      fat: 18,
      fiber: 4,
      alcohol_units: null,
      image_url: null,
      notes: null,
      health_tips: null,
    } as any);

    const onCardDataChange = jest.fn();
    const { getByLabelText, getByText } = render(
      <RecordQualityCardView
        {...(baseAdjustCard({
          adjust_record: {
            ...baseAdjustCard().adjust_record,
            meal_type: 'lunch',
            food_items: '一碗虾滑鸡蛋汤',
          },
        }) as any)}
        onCardDataChange={onCardDataChange}
      />,
    );

    fireEvent.changeText(getByLabelText('食物描述'), '两碗虾滑鸡蛋汤');

    await act(async () => {
      fireEvent.press(getByText('保存修正'));
    });

    await waitFor(() => expect(mockRecalculate).toHaveBeenCalledTimes(1));
    expect(mockRecalculate).toHaveBeenCalledWith(123, {
      meal_type: 'lunch',
      food_items: '两碗虾滑鸡蛋汤',
      expected_updated_at: '2026-08-20T12:00:00Z',
    }, '00000000-0000-4000-8000-000000000001');
    expect(mockUpdate).not.toHaveBeenCalled();
  });

  it('keeps manual nutrition edits on the ordinary PUT path when food is unchanged', async () => {
    mockUpdate.mockResolvedValue({
      id: 123,
      meal_type: 'dinner',
      food_items: '100克葡萄 五十克饼干',
      calories: 245,
      protein: 6,
      carbs: 52,
      fat: 4,
      fiber: 5,
    } as any);

    const { getByLabelText, getByText } = render(
      <RecordQualityCardView {...(baseAdjustCard() as any)} onCardDataChange={jest.fn()} />,
    );

    fireEvent.press(getByText('晚餐'));
    fireEvent.changeText(getByLabelText('热量'), '245');
    fireEvent.changeText(getByLabelText('蛋白'), '6');
    fireEvent.changeText(getByLabelText('膳食纤维'), '5');

    await act(async () => {
      fireEvent.press(getByText('保存修正'));
    });

    await waitFor(() => expect(mockUpdate).toHaveBeenCalledTimes(1));
    expect(mockUpdate).toHaveBeenCalledWith(123, {
      meal_type: 'dinner',
      food_items: '100克葡萄 五十克饼干',
      calories: 245,
      protein: 6,
      carbs: 52,
      fat: 4,
      fiber: 5,
    });
    expect(mockRecalculate).not.toHaveBeenCalled();
  });

  it('authoritatively replaces all five nutrients, including explicit nulls', async () => {
    mockRecalculate.mockResolvedValue({
      id: 123,
      meal_type: 'snack',
      food_items: '两碗水果酸奶',
      calories: 310,
      protein: null,
      carbs: 44,
      fat: null,
      fiber: null,
      updated_at: null,
    } as any);

    const onCardDataChange = jest.fn();
    const { getByLabelText, getByText } = render(
      <RecordQualityCardView {...(baseAdjustCard() as any)} onCardDataChange={onCardDataChange} />,
    );

    fireEvent.changeText(getByLabelText('食物描述'), '两碗水果酸奶');
    await act(async () => {
      fireEvent.press(getByText('保存修正'));
    });

    await waitFor(() => expect(onCardDataChange).toHaveBeenCalledTimes(1));
    const next = onCardDataChange.mock.calls[0][0];
    expect(next.adjust_record).toEqual({
      record_id: 123,
      meal_type: 'snack',
      food_items: '两碗水果酸奶',
      calories: 310,
      protein: null,
      carbs: 44,
      fat: null,
      fiber: null,
      updated_at: null,
    });
    expect(next).toEqual(expect.objectContaining({
      calories: 310,
      protein: null,
      carbs: 44,
      fat: null,
      fiber: null,
      updated_at: null,
    }));
    expect(next.metrics).toEqual([
      { label: '热量', value: '310kcal' },
      { label: '碳水', value: '44g' },
    ]);
    expect(mockUpdate).not.toHaveBeenCalled();
  });

  it('invalidates stale daily progress and guidance after nutrition is recalculated', async () => {
    mockRecalculate.mockResolvedValue({
      id: 123,
      meal_type: 'lunch',
      food_items: '两碗虾滑鸡蛋汤',
      calories: 360,
      protein: 32,
      carbs: 16,
      fat: 18,
      fiber: 4,
    } as any);

    const onCardDataChange = jest.fn();
    const { getByLabelText, getByText } = render(
      <RecordQualityCardView
        {...(baseAdjustCard({
          progress: {
            calories_total: 180,
            protein_total_g: 16,
            protein_target_g: 113,
            remaining_protein_g: 97,
          },
          primary_judgement: '旧营养判断',
          personal_cautions: ['旧食材提醒'],
          next_action: '旧下一餐建议',
          next_meal_detail: { summary: '旧下一餐详情' },
          expanded_sections: ['adjust_record', 'next_meal'],
        }) as any)}
        onCardDataChange={onCardDataChange}
      />,
    );

    fireEvent.changeText(getByLabelText('食物描述'), '两碗虾滑鸡蛋汤');
    await act(async () => {
      fireEvent.press(getByText('保存修正'));
    });

    await waitFor(() => expect(onCardDataChange).toHaveBeenCalledTimes(1));
    const next = onCardDataChange.mock.calls[0][0];
    expect(next).not.toHaveProperty('progress');
    expect(next).not.toHaveProperty('primary_judgement');
    expect(next).not.toHaveProperty('personal_cautions');
    expect(next).not.toHaveProperty('next_action');
    expect(next).not.toHaveProperty('next_meal_detail');
    expect(next.expanded_sections).toEqual([]);
  });

  it('refreshes the card face and collapses the editor after a successful save', async () => {
    mockUpdate.mockResolvedValue({
      id: 123,
      meal_type: 'dinner',
      food_items: '鸡胸肉 200g',
      calories: 480,
      protein: 46,
      carbs: 30,
      fat: 8.4,
      fiber: null,
    } as any);

    const onCardDataChange = jest.fn();
    const { getByText } = render(
      <RecordQualityCardView {...(baseAdjustCard() as any)} onCardDataChange={onCardDataChange} />,
    );

    await act(async () => {
      fireEvent.press(getByText('保存修正'));
    });

    await waitFor(() => expect(onCardDataChange).toHaveBeenCalledTimes(1));
    const next = onCardDataChange.mock.calls[0][0];
    // 卡面 summary/metrics 就地刷新为保存后的新值
    expect(next.summary).toBe('晚餐 · 480 kcal · 蛋白 46g · 碳水 30g · 脂肪 8.4g');
    expect(next.metrics).toEqual([
      { label: '热量', value: '480kcal' },
      { label: '蛋白', value: '46g' },
      { label: '碳水', value: '30g' },
      { label: '脂肪', value: '8.4g' },
    ]);
    // 编辑器收起 (adjust_record 移出 expanded_sections) + 成功标记
    expect(next.expanded_sections).not.toContain('adjust_record');
    expect(next.adjust_saved).toBe(true);
  });

  it('shows the updated marker on the card face after a save', () => {
    const { getByText, queryByText } = render(
      <RecordQualityCardView
        {...(baseAdjustCard({ expanded_sections: [], adjust_saved: true }) as any)}
        onCardDataChange={jest.fn()}
      />,
    );
    expect(getByText('已更新')).toBeTruthy();
    // 编辑器仍未展开
    expect(queryByText('就地修正这条记录，保存后直接更新')).toBeNull();
  });

  it('surfaces an inline error and keeps user input when an ordinary save fails', async () => {
    mockUpdate.mockRejectedValue(new Error('network'));

    const onCardDataChange = jest.fn();
    const { getByLabelText, getByText } = render(
      <RecordQualityCardView {...(baseAdjustCard() as any)} onCardDataChange={onCardDataChange} />,
    );

    fireEvent.changeText(getByLabelText('热量'), '250');
    await act(async () => {
      fireEvent.press(getByText('保存修正'));
    });

    await waitFor(() => expect(getByText('保存失败，请重试')).toBeTruthy());
    // fail-loud: 不吞错, 不刷新卡面, 保留用户输入, 编辑器仍在
    expect(onCardDataChange).not.toHaveBeenCalled();
    expect((getByLabelText('热量').props as any).value).toBe('250');
    expect(getByText('保存修正')).toBeTruthy();
  });

  it('does not fall back to PUT or collapse when nutrition recalculation fails', async () => {
    mockRecalculate.mockRejectedValue(new Error('nutrition service unavailable'));

    const onCardDataChange = jest.fn();
    const { getByLabelText, getByText } = render(
      <RecordQualityCardView {...(baseAdjustCard() as any)} onCardDataChange={onCardDataChange} />,
    );

    fireEvent.changeText(getByLabelText('食物描述'), '两碗葡萄和饼干');
    await act(async () => {
      fireEvent.press(getByText('保存修正'));
    });

    await waitFor(() => expect(getByText('营养重新计算失败，请重试')).toBeTruthy());
    expect(mockRecalculate).toHaveBeenCalledTimes(1);
    expect(mockUpdate).not.toHaveBeenCalled();
    expect(onCardDataChange).not.toHaveBeenCalled();
    expect((getByLabelText('食物描述').props as any).value).toBe('两碗葡萄和饼干');
    const firstOperationKey = mockRecalculate.mock.calls[0][2];
    expect(typeof firstOperationKey).toBe('string');

    await act(async () => {
      fireEvent.press(getByText('保存修正'));
    });
    await waitFor(() => expect(mockRecalculate).toHaveBeenCalledTimes(2));
    expect(mockRecalculate.mock.calls[1][2]).toBe(firstOperationKey);
  });

  it('generates a new recalculation operation key when the payload changes', async () => {
    mockRecalculate.mockRejectedValue(new Error('nutrition service unavailable'));

    const { getByLabelText, getByText } = render(
      <RecordQualityCardView {...(baseAdjustCard() as any)} onCardDataChange={jest.fn()} />,
    );

    fireEvent.changeText(getByLabelText('食物描述'), '两碗葡萄和饼干');
    await act(async () => {
      fireEvent.press(getByText('保存修正'));
    });
    await waitFor(() => expect(mockRecalculate).toHaveBeenCalledTimes(1));
    const firstOperationKey = mockRecalculate.mock.calls[0][2];

    fireEvent.changeText(getByLabelText('食物描述'), '两碗葡萄和苹果');
    await act(async () => {
      fireEvent.press(getByText('保存修正'));
    });
    await waitFor(() => expect(mockRecalculate).toHaveBeenCalledTimes(2));
    const secondOperationKey = mockRecalculate.mock.calls[1][2];

    fireEvent.press(getByLabelText('餐次 午餐'));
    await act(async () => {
      fireEvent.press(getByText('保存修正'));
    });
    await waitFor(() => expect(mockRecalculate).toHaveBeenCalledTimes(3));
    const thirdOperationKey = mockRecalculate.mock.calls[2][2];

    expect(typeof firstOperationKey).toBe('string');
    expect(secondOperationKey).not.toBe(firstOperationKey);
    expect(thirdOperationKey).not.toBe(secondOperationKey);
  });

  it('uses the same normalized food text for the recalculation request and operation signature', async () => {
    mockRecalculate.mockRejectedValue(new Error('nutrition service unavailable'));

    const { getByLabelText, getByText } = render(
      <RecordQualityCardView {...(baseAdjustCard() as any)} onCardDataChange={jest.fn()} />,
    );

    fireEvent.changeText(getByLabelText('食物描述'), '两  碗葡萄  和饼干');
    await act(async () => {
      fireEvent.press(getByText('保存修正'));
    });

    await waitFor(() => expect(mockRecalculate).toHaveBeenCalledTimes(1));
    expect(mockRecalculate).toHaveBeenCalledWith(123, {
      meal_type: 'snack',
      food_items: '两 碗葡萄 和饼干',
      expected_updated_at: '2026-08-20T12:00:00Z',
    }, expect.any(String));
  });

  it('blocks food recalculation when the current record revision is missing', () => {
    const { getByLabelText, getByText } = render(
      <RecordQualityCardView
        {...(baseAdjustCard({
          adjust_record: {
            ...baseAdjustCard().adjust_record,
            updated_at: undefined,
          },
        }) as any)}
        onCardDataChange={jest.fn()}
      />,
    );

    fireEvent.changeText(getByLabelText('食物描述'), '两碗葡萄和饼干');

    expect(getByText('记录版本缺失，请取消并重新打开或刷新后再修改')).toBeTruthy();
    const saveButton = getByLabelText('保存修正');
    expect(saveButton).toHaveAccessibilityState({ disabled: true, busy: false });
    fireEvent.press(saveButton);
    expect(mockRecalculate).not.toHaveBeenCalled();
    expect(mockUpdate).not.toHaveBeenCalled();
  });

  it('fails loudly without transport when secure randomness is unavailable', async () => {
    installTestCrypto(undefined);
    mockRecalculate.mockResolvedValue({
      id: 123,
      meal_type: 'snack',
      food_items: '两碗葡萄和饼干',
      calories: 460,
      protein: 6,
      carbs: 104,
      fat: 8,
      fiber: 4,
    } as any);

    const { getByLabelText, getByText } = render(
      <RecordQualityCardView {...(baseAdjustCard() as any)} onCardDataChange={jest.fn()} />,
    );

    fireEvent.changeText(getByLabelText('食物描述'), '两碗葡萄和饼干');
    await act(async () => {
      fireEvent.press(getByText('保存修正'));
    });

    await waitFor(() => expect(getByText('无法安全生成保存标识，请取消并重新打开后再试')).toBeTruthy());
    expect(mockRecalculate).not.toHaveBeenCalled();
    expect(mockUpdate).not.toHaveBeenCalled();
    expect((getByLabelText('食物描述').props as any).value).toBe('两碗葡萄和饼干');
    expect(getByLabelText('保存修正')).toHaveAccessibilityState({ disabled: true, busy: false });
  });

  it('blocks stale-revision retries and keeps input after a recalculation conflict', async () => {
    mockRecalculate.mockRejectedValue(Object.assign(new Error('conflict'), {
      response: { status: 409, data: { detail: '饮食记录已更新，请刷新后重试' } },
    }));

    const onCardDataChange = jest.fn();
    const { getByLabelText, getByText } = render(
      <RecordQualityCardView
        {...(baseAdjustCard({
          adjust_record: {
            ...baseAdjustCard().adjust_record,
            updated_at: '2026-08-20T12:00:00Z',
          },
        }) as any)}
        onCardDataChange={onCardDataChange}
      />,
    );

    fireEvent.changeText(getByLabelText('食物描述'), '两碗葡萄和饼干');
    await act(async () => {
      fireEvent.press(getByText('保存修正'));
    });

    await waitFor(() => expect(getByText('记录已在其他位置更新，请取消并重新打开后再修改')).toBeTruthy());
    expect(mockRecalculate).toHaveBeenCalledWith(123, {
      meal_type: 'snack',
      food_items: '两碗葡萄和饼干',
      expected_updated_at: '2026-08-20T12:00:00Z',
    }, '00000000-0000-4000-8000-000000000001');
    expect((getByLabelText('食物描述').props as any).value).toBe('两碗葡萄和饼干');
    const saveButton = getByLabelText('保存修正');
    expect(saveButton).toHaveAccessibilityState({ disabled: true, busy: false });

    await act(async () => {
      fireEvent.press(saveButton);
    });
    expect(mockRecalculate).toHaveBeenCalledTimes(1);
    expect(mockUpdate).not.toHaveBeenCalled();
    expect(onCardDataChange).not.toHaveBeenCalled();
  });

  it('does not write anything when the user cancels', () => {
    const onCardDataChange = jest.fn();
    const { getByText, queryByText } = render(
      <RecordQualityCardView {...(baseAdjustCard() as any)} onCardDataChange={onCardDataChange} />,
    );

    fireEvent.press(getByText('取消'));

    expect(mockRecalculate).not.toHaveBeenCalled();
    expect(mockUpdate).not.toHaveBeenCalled();
    expect(onCardDataChange).not.toHaveBeenCalled();
    expect(queryByText('就地修正这条记录，保存后直接更新')).toBeNull();
  });

  it('expands the inline editor through the ui.inline.expand registry channel', () => {
    const descriptor = {
      type: 'record_quality',
      data: {
        domain: 'diet',
        title: '加餐已记录',
        summary: '230 kcal · 蛋白 3g',
        metrics: [{ label: '热量', value: '230kcal' }],
        boundary: '健康管理建议，不替代医生诊断或治疗。',
      },
      actions: [
        {
          id: 'adjust-record',
          label: '调整记录',
          action: 'ui.inline.expand',
          payload: {
            target: 'adjust_record',
            patch: {
              expanded_sections: ['adjust_record'],
              adjust_record: {
                record_id: 123,
                meal_type: 'snack',
                food_items: '100克葡萄 五十克饼干',
                calories: 230,
                protein: 3,
                carbs: 52,
                fat: 4,
              },
            },
          },
        },
      ],
    } as any;

    const onAction = jest.fn();
    const element = renderCard(descriptor, { onAction });
    expect(element).not.toBeNull();

    const { getByText, getByLabelText, queryByText } = render(element!);
    // 展开前编辑器不在
    expect(queryByText('就地修正这条记录，保存后直接更新')).toBeNull();

    fireEvent.press(getByText('调整记录'));

    // ui.inline.expand 走本地展开通道, 不派发到 onAction
    expect(onAction).not.toHaveBeenCalled();
    // 编辑器就地展开且已 seed
    expect(getByText('就地修正这条记录，保存后直接更新')).toBeTruthy();
    expect((getByLabelText('食物描述').props as any).value).toBe('100克葡萄 五十克饼干');
  });

  it.each([
    ['known-null', null],
    ['timestamp', '2026-08-20T12:00:00Z'],
  ])('preserves an action-seed-only %s revision for recalculation', async (_label, updatedAt) => {
    mockRecalculate.mockResolvedValue({
      id: 123,
      meal_type: 'snack',
      food_items: '两碗葡萄和饼干',
      calories: 460,
      protein: 6,
      carbs: 104,
      fat: 8,
      fiber: 4,
    } as any);
    const descriptor = {
      type: 'record_quality',
      data: {
        domain: 'diet',
        title: '加餐已记录',
        summary: '230 kcal · 蛋白 3g',
        metrics: [{ label: '热量', value: '230kcal' }],
        boundary: '健康管理建议，不替代医生诊断或治疗。',
      },
      actions: [{
        id: 'adjust-record',
        label: '调整记录',
        action: 'ui.inline.expand',
        payload: {
          target: 'adjust_record',
          patch: {
            expanded_sections: ['adjust_record'],
            adjust_record: {
              record_id: 123,
              meal_type: 'snack',
              food_items: '100克葡萄 五十克饼干',
              calories: 230,
              protein: 3,
              carbs: 52,
              fat: 4,
              fiber: 2,
              updated_at: updatedAt,
            },
          },
        },
      }],
    } as any;

    const element = renderCard(descriptor, { onAction: jest.fn() });
    const screen = render(element!);
    fireEvent.press(screen.getByText('调整记录'));
    fireEvent.changeText(screen.getByLabelText('食物描述'), '两碗葡萄和饼干');
    await act(async () => {
      fireEvent.press(screen.getByText('保存修正'));
    });

    await waitFor(() => expect(mockRecalculate).toHaveBeenCalledTimes(1));
    expect(mockRecalculate).toHaveBeenCalledWith(123, {
      meal_type: 'snack',
      food_items: '两碗葡萄和饼干',
      expected_updated_at: updatedAt,
    }, expect.any(String));
  });
});

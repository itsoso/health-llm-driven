/**
 * RevaHeroCard —— 时间感知 Hero(now-action)行为测试。
 *
 * 覆盖重设计核心:Hero 不再是清晨第一项,而是后端 now-item 的 title/why/时点 + 内联完成;
 * 无 now → 空态行(「今天的事都安排好了」);可完成时露出「完成」并触发 onComplete。
 */
import React from 'react';
import { render, fireEvent } from '@testing-library/react-native';
import RevaHeroCard from '../components/home/RevaHeroCard';

describe('RevaHeroCard (time-aware now-action)', () => {
  it('renders the now-item title/subtitle/time (not a morning weigh-in by default)', () => {
    const { getByText, queryByText } = render(
      <RevaHeroCard
        readiness={72}
        hasNow
        nowTitle="服用二甲双胍"
        nowSubtitle="随午餐服用,减少肠胃反应"
        nowTime="12:30"
        nowLever="现在该做 · 中午"
        canComplete
        onPressAction={() => {}}
        onComplete={() => {}}
      />,
    );
    expect(getByText('服用二甲双胍')).toBeTruthy();
    expect(getByText('随午餐服用,减少肠胃反应')).toBeTruthy();
    expect(getByText('12:30')).toBeTruthy();
    expect(getByText('现在该做 · 中午')).toBeTruthy();
    // 就绪分仅作支撑上下文(小环),不应出现空态文案。
    expect(queryByText('今天的事都安排好了')).toBeNull();
  });

  it('shows inline 完成 only when canComplete, and fires onComplete', () => {
    const onComplete = jest.fn();
    const { getByText, getByLabelText } = render(
      <RevaHeroCard
        readiness={null}
        hasNow
        nowTitle="补水 250ml"
        canComplete
        onPressAction={() => {}}
        onComplete={onComplete}
      />,
    );
    expect(getByText('完成')).toBeTruthy();
    fireEvent.press(getByLabelText('完成 补水 250ml'));
    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  it('hides 完成 when not completable', () => {
    const { queryByText } = render(
      <RevaHeroCard
        readiness={88}
        hasNow
        nowTitle="傍晚散步 20 分钟"
        canComplete={false}
        onPressAction={() => {}}
      />,
    );
    expect(queryByText('完成')).toBeNull();
  });

  it('renders graceful empty state when there is no now-item', () => {
    const onPress = jest.fn();
    const { getByText, getByLabelText } = render(
      <RevaHeroCard
        readiness={null}
        hasNow={false}
        nowTitle="补齐今天记录"
        onPressAction={onPress}
      />,
    );
    expect(getByText('今天的事都安排好了')).toBeTruthy();
    expect(getByText('补齐今天记录')).toBeTruthy();
    fireEvent.press(getByLabelText('补齐今天记录'));
    expect(onPress).toHaveBeenCalledTimes(1);
  });

  it('does not fire onComplete while completing (action-lock via disabled)', () => {
    const onComplete = jest.fn();
    const { queryByLabelText } = render(
      <RevaHeroCard
        readiness={60}
        hasNow
        nowTitle="服药"
        canComplete
        completing
        onPressAction={() => {}}
        onComplete={onComplete}
      />,
    );
    const btn = queryByLabelText('完成 服药');
    if (btn) fireEvent.press(btn);
    expect(onComplete).not.toHaveBeenCalled();
  });
});

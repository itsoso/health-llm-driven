import React from 'react';
import { ScrollView, StyleSheet } from 'react-native';
import { fireEvent, render } from '@testing-library/react-native';
import SafeTableMarkdown from '../SafeTableMarkdown';

describe('native HTML table preview', () => {
  const source = '```html\n<table><caption>本周睡眠</caption><tr><th>日期</th><th>评分</th><th>时长</th><th>深睡</th><th>REM</th><th>清醒</th></tr><tr><td>周一</td><td>78</td><td>7小时10分</td><td></td><td>A | B</td><td>&lt;img src=x&gt;</td></tr></table>\n```';

  it('renders actual native wide rows with no lost empty cell or interpreted markup', () => {
    const view = render(<SafeTableMarkdown content={source} />);
    const scroll = view.UNSAFE_getByType(ScrollView);
    expect(scroll.props.horizontal).toBe(true);
    expect(view.getByText('本周睡眠')).toBeTruthy();
    expect(view.getByText('7小时10分')).toBeTruthy();
    expect(view.getByText('A | B')).toBeTruthy();
    expect(view.getByText('<img src=x>')).toBeTruthy();
    expect(view.getAllByRole('header')).toHaveLength(6);
    const width = StyleSheet.flatten(view.getByTestId('safe-html-cell-0-4').props.style).width;
    expect(width).toBe(132);
    expect(view.queryByText(source)).toBeNull();
    fireEvent.press(view.getByRole('button', { name: '查看 HTML 源码' }));
    expect(view.getByText(source)).toBeTruthy();
    fireEvent.press(view.getByRole('button', { name: '收起 HTML 源码' }));
    expect(view.queryByText(source)).toBeNull();
  });

  it('changes from streaming source to a preview only on completion', () => {
    const view = render(<SafeTableMarkdown content={source} allowHtmlTables={false} />);
    expect(view.queryByTestId('safe-html-table')).toBeNull();
    view.rerender(<SafeTableMarkdown content={source} allowHtmlTables />);
    expect(view.getByTestId('safe-html-table')).toBeTruthy();
  });

  it('renders malformed HTML as selectable literal text', () => {
    const html = '<table><tr><td onclick="alert(1)">7小时';
    const view = render(<SafeTableMarkdown content={html} />);
    expect(view.getByText(html).props.selectable).toBe(true);
    expect(view.queryByTestId('safe-html-table')).toBeNull();
  });
});

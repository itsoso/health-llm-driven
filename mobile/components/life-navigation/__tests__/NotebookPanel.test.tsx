import React, { useState } from 'react';
import { fireEvent, render } from '@testing-library/react-native';
import NotebookPanel from '../NotebookPanel';
import type { NotebookEntry } from '../../../types/lifeNavigation';

const initial: NotebookEntry[] = [
    { id: '11111111-1111-4111-8111-111111111111', title: 'Alpha', body: '第一条' },
    { id: '22222222-2222-4222-8222-222222222222', title: 'Beta', body: '第二条' },
];
function Harness({ notes = initial }: { notes?: NotebookEntry[] }) {
    const [draft, setDraft] = useState(notes);
    return <NotebookPanel notes={draft} disabled={false} onChange={setDraft} onDelete={jest.fn()} />;
}
it('searches title and body without changing the document being edited', () => {
    const view = render(<Harness />);
    fireEvent.changeText(view.getByLabelText('搜索笔记'), ' alpha ');
    expect(view.queryByLabelText('打开笔记 Beta')).toBeNull();
    fireEvent.press(view.getByLabelText('打开笔记 Alpha'));
    fireEvent.changeText(view.getByLabelText('笔记标题'), '不再匹配');
    fireEvent.changeText(view.getByLabelText('笔记正文'), '仍然属于第一条');
    expect(view.getByLabelText('笔记正文').props.value).toBe('仍然属于第一条');
    fireEvent.press(view.getByLabelText('返回笔记列表'));
    expect(view.getByText('没有匹配的笔记')).toBeTruthy();
    fireEvent.changeText(view.getByLabelText('搜索笔记'), '第二条');
    fireEvent.press(view.getByLabelText('打开笔记 Beta'));
    expect(view.getByLabelText('笔记正文').props.value).toBe('第二条');
});
it('creates an empty note, bounds input, and prevents writes while saving', () => {
    const change = jest.fn(), remove = jest.fn();
    const view = render(<NotebookPanel notes={initial} disabled={false} onChange={change} onDelete={remove} />);
    fireEvent.press(view.getByLabelText('新建笔记'));
    expect(change).toHaveBeenCalledWith([expect.objectContaining({ title: '', body: '' }), ...initial]);
    fireEvent.press(view.getByLabelText('打开笔记 Alpha'));
    expect(view.getByLabelText('笔记标题').props.maxLength).toBe(200);
    expect(view.getByLabelText('笔记正文').props.maxLength).toBe(20000);
    view.rerender(<NotebookPanel notes={initial} disabled onChange={change} onDelete={remove} />);
    change.mockClear();
    fireEvent.changeText(view.getByLabelText('笔记正文'), '不得写入');
    fireEvent.press(view.getByLabelText('删除笔记'));
    expect(change).not.toHaveBeenCalled();
    expect(remove).not.toHaveBeenCalled();
});
it('caps notebook creation at 100 entries', () => {
    const change = jest.fn();
    const view = render(<NotebookPanel notes={Array.from({ length: 100 }, (_, i) => ({ ...initial[0], id: String(i) }))} disabled={false} onChange={change} onDelete={jest.fn()} />);
    fireEvent.press(view.getByLabelText('新建笔记'));
    expect(change).not.toHaveBeenCalled();
    expect(view.getByLabelText('新建笔记').props.accessibilityState.disabled).toBe(true);
});

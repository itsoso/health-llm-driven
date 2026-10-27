import { act, fireEvent, render, screen, cleanup } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { useNavigationParam } from './useNavigationParam';
const sections = { plan: '计划', practice: '练习' } as const;
const tabs = { today: '今日', exam: '备考学习' } as const;
function Example() {
 const [tab, setTab] = useNavigationParam('tab', tabs, '今日');
 const [section, setSection] = useNavigationParam('study', sections, '计划');
 return <><span>{tab}/{section}</span><button onClick={() => setTab('备考学习')}>Exam</button><button onClick={() => setSection('练习')}>Practice</button></>;
}
afterEach(() => { cleanup(); window.history.replaceState(null, '', '/'); });
it('loads shared links and preserves unrelated query parameters and hash', () => {
 window.history.replaceState({ marker: 1, __NA: true }, '', '/agenda?navigation=week&tab=exam&study=plan#top');
 render(<Example/>);
 expect(screen.getByText('备考学习/计划')).toBeTruthy();
 fireEvent.click(screen.getByText('Practice'));
 expect(location.search).toContain('navigation=week');
 expect(location.hash).toBe('#top');
 expect(history.state.marker).toBe(1);
 expect(history.state.__NA).toBeUndefined();
});
it('writes selections and follows back/forward events without remounting', () => {
 window.history.replaceState(null, '', '/agenda?navigation=week');
 render(<Example/>);
 fireEvent.click(screen.getByText('Exam')); fireEvent.click(screen.getByText('Practice'));
 expect(location.search).toBe('?navigation=week&tab=exam&study=practice');
 act(() => { history.replaceState(null, '', '/agenda?navigation=week&tab=today'); window.dispatchEvent(new PopStateEvent('popstate')); });
 expect(screen.getByText('今日/计划')).toBeTruthy();
});
it('uses safe defaults for unknown values', () => {
 history.replaceState(null, '', '/agenda?navigation=week&tab=invalid&study=invalid');
 render(<Example/>); expect(screen.getByText('今日/计划')).toBeTruthy();
});

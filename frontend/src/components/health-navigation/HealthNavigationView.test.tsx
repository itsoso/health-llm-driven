import { describe,it,expect,vi } from 'vitest';
import { render,screen,waitFor,fireEvent,act } from '@testing-library/react';
vi.mock('@/contexts/AuthContext',()=>({useAuth:()=>({user:{id:1}})}));
const get=vi.fn(),post=vi.fn();
vi.mock('@/services/api/client',()=>({api:{get:(...args:unknown[])=>get(...args),post:(...args:unknown[])=>post(...args)}}));
import HealthNavigationView from './HealthNavigationView';
it('shows source coverage without inventing completion rate and links private planning separately',async()=>{
 get.mockResolvedValue({data:{availability:'ready',timezone:'Asia/Shanghai',source_as_of:null,expires_at:'2099-01-01T00:00:00Z',review_window:{start_date:'2026-10-03',end_date:'2026-10-09'},review:{recorded_days:2,window_days:7,completed_occurrences:1,skipped_occurrences:0,deferred_occurrences:0,unknown_occurrences:1,claim_boundary:'不证明因果'},actions:[]}});
 render(<HealthNavigationView/>);
 await waitFor(()=>expect(screen.getByText('已记录 2/7 天')).toBeTruthy());
 expect(screen.queryByText(/完成率/)).toBeNull();
 expect(screen.getByText('安排我的一周').getAttribute('href')).toBe('/agenda?navigation=week');
});

it('releases a pending refresh after rereading changes the view epoch',async()=>{
 let finish!:()=>void;post.mockImplementation(()=>new Promise<void>(resolve=>{finish=resolve}));
 render(<HealthNavigationView/>);
 const button=screen.getAllByText('更新今日健康行动').at(-1)! as HTMLButtonElement;
 fireEvent.click(button);expect(button.disabled).toBe(true);
 fireEvent.click(screen.getAllByText('重新读取').at(-1)!);
 await act(async()=>{finish()});
 await waitFor(()=>expect(button.disabled).toBe(false));
});

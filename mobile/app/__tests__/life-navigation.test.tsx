import React from 'react';
import {render,waitFor,fireEvent} from '@testing-library/react-native';
jest.mock('../../hooks/useAuth',()=>({useAuth:()=>({user:{id:1}})}));
jest.mock('expo-router',()=>({useRouter:()=>({push:jest.fn()}),Stack:{Screen:()=>null},useFocusEffect:(cb:()=>void)=>require('react').useEffect(cb,[cb])}));
jest.mock('../../services/lifeNavigation',()=>({fetchLifeWorkspace:jest.fn(),saveLifeWorkspace:jest.fn()}));
import {fetchLifeWorkspace,saveLifeWorkspace} from '../../services/lifeNavigation';
import Screen from '../life-navigation';
it('only reports a personal task saved after the server confirms',async()=>{
 (fetchLifeWorkspace as jest.Mock).mockResolvedValue({revision:0,data:{weeks:{}}});
 (saveLifeWorkspace as jest.Mock).mockRejectedValue({response:{status:409}});
 const view=render(<Screen/>);
 await waitFor(()=>view.getByText('还没有个人安排。'));
 fireEvent.changeText(view.getByLabelText('个人任务标题'),'读书');
 fireEvent.press(view.getByText('加入今日安排'));
 await waitFor(()=>view.getByText('另一设备已更新，草稿已保留，请重新读取后核对。'));
 expect(view.queryByText('已保存个人安排')).toBeNull();
 expect(view.getByLabelText('个人任务标题').props.value).toBe('读书');
});

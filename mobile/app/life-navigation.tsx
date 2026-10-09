import React from 'react';
import { Text } from 'react-native';
import {useRouter} from 'expo-router';
import { useAuth } from '../hooks/useAuth';
import Workspace from '../components/life-navigation/Workspace';
export { mondayOf as personalWeekStart } from '../utils/lifeNavigationModel';
export default function LifeNavigationScreen() { const { user } = useAuth();const router=useRouter(); return user ? <Workspace key={user.id} owner={user.id} onViewHealth={()=>router.push('/my-progress?navigation=week' as any)}/> : <Text>请登录后查看本人安排。</Text>; }

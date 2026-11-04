import React from 'react';
import { Text } from 'react-native';
import {useLocalSearchParams, useRouter} from 'expo-router';
import { useAuth } from '../hooks/useAuth';
import Workspace from '../components/life-navigation/Workspace';
export { mondayOf as personalWeekStart } from '../utils/lifeNavigationModel';
export default function LifeNavigationScreen() { const { user } = useAuth();const router=useRouter();const params=useLocalSearchParams<{tab?:string;study?:string}>();const exam=params.tab==='exam'; return user ? <Workspace key={user.id} owner={user.id} initialTab={exam?'备考学习':undefined} initialExamSection={exam&&params.study==='practice'?'练习与错题':undefined} onViewHealth={()=>router.push('/my-progress?navigation=week' as any)}/> : <Text>请登录后查看本人安排。</Text>; }

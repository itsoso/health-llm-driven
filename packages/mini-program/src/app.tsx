import { PropsWithChildren } from 'react';
import { useLaunch } from '@tarojs/taro';
import Taro from '@tarojs/taro';
import './app.scss';

function App({ children }: PropsWithChildren) {
  useLaunch(() => {
    console.log('App launched.');
    
    // 全局错误监听
    Taro.onError((error) => {
      console.error('全局错误:', error);
    });
    
    // 未处理的Promise拒绝
    Taro.onUnhandledRejection((res) => {
      console.error('未处理的Promise拒绝:', res);
    });
  });

  // 添加错误边界
  try {
    return children;
  } catch (error) {
    console.error('App渲染错误:', error);
    return null;
  }
}

export default App;


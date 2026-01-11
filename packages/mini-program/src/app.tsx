import { PropsWithChildren } from 'react';
import { useLaunch, useErrorHandler } from '@tarojs/taro';
import './app.scss';

function App({ children }: PropsWithChildren) {
  useLaunch(() => {
    console.log('App launched.');
  });

  // 错误处理
  useErrorHandler((error: Error) => {
    console.error('App Error:', error);
    console.error('Error Stack:', error.stack);
    // 可以在这里添加错误上报逻辑
  });

  return children;
}

export default App;


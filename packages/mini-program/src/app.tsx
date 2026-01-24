import { PropsWithChildren, useState, useEffect } from 'react';
import { useLaunch } from '@tarojs/taro';
import Taro from '@tarojs/taro';
import PrivacyModal from './components/PrivacyModal';
import './app.scss';

const PRIVACY_AGREED_KEY = 'privacy_agreed';

function App({ children }: PropsWithChildren) {
  const [showPrivacyModal, setShowPrivacyModal] = useState(false);

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

    // 检查是否已同意隐私协议
    checkPrivacyAgreement();
  });

  const checkPrivacyAgreement = () => {
    try {
      const agreed = Taro.getStorageSync(PRIVACY_AGREED_KEY);
      if (!agreed) {
        // 延迟显示弹窗，确保页面已加载
        setTimeout(() => {
          setShowPrivacyModal(true);
        }, 500);
      }
    } catch (error) {
      console.error('检查隐私协议失败:', error);
    }
  };

  const handleAgree = () => {
    try {
      Taro.setStorageSync(PRIVACY_AGREED_KEY, 'true');
      setShowPrivacyModal(false);
      Taro.showToast({
        title: '欢迎使用',
        icon: 'success',
      });
    } catch (error) {
      console.error('保存隐私协议同意状态失败:', error);
    }
  };

  const handleDisagree = () => {
    Taro.showModal({
      title: '温馨提示',
      content: '如果不同意隐私保护指引，将无法使用本小程序的功能。你可以点击"查看详情"了解更多信息。',
      confirmText: '退出小程序',
      cancelText: '重新查看',
      success: (res) => {
        if (res.confirm) {
          // 用户选择退出
          // 注意：小程序无法直接退出，只能提示用户手动关闭
          Taro.showToast({
            title: '请手动关闭小程序',
            icon: 'none',
            duration: 3000,
          });
        } else {
          // 用户选择重新查看
          setShowPrivacyModal(true);
        }
      },
    });
  };

  // 添加错误边界
  try {
    return (
      <>
        {children}
        <PrivacyModal
          visible={showPrivacyModal}
          onAgree={handleAgree}
          onDisagree={handleDisagree}
        />
      </>
    );
  } catch (error) {
    console.error('App渲染错误:', error);
    return null;
  }
}

export default App;


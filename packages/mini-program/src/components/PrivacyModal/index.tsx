/**
 * 隐私协议弹窗组件
 * 用于首次使用时展示隐私协议
 */
import { View, Text, Button } from '@tarojs/components';
import Taro from '@tarojs/taro';
import './index.scss';

interface PrivacyModalProps {
  visible: boolean;
  onAgree: () => void;
  onDisagree: () => void;
}

export default function PrivacyModal({ visible, onAgree, onDisagree }: PrivacyModalProps) {
  if (!visible) return null;

  const handleViewDetail = () => {
    Taro.navigateTo({
      url: '/pages/privacy/index'
    });
  };

  return (
    <View className="privacy-modal-mask">
      <View className="privacy-modal">
        <View className="modal-header">
          <Text className="modal-icon">🔒</Text>
          <Text className="modal-title">用户隐私保护提示</Text>
        </View>

        <View className="modal-content">
          <Text className="content-text">
            欢迎使用"自由是自律的泡沫"健康管理小程序！
          </Text>
          
          <Text className="content-text">
            在使用我们的服务前，请你认真阅读
            <Text className="link-text" onClick={handleViewDetail}>《隐私保护指引》</Text>
            ，了解我们如何收集、使用和保护你的个人信息。
          </Text>

          <View className="highlight-box">
            <Text className="highlight-title">📸 特别说明</Text>
            <Text className="highlight-text">
              在"饮食记录"功能中，我们会请求访问你的相册或相机，用于：
            </Text>
            <Text className="highlight-item">• 拍摄或选择食物照片</Text>
            <Text className="highlight-item">• AI智能识别食物种类和营养成分</Text>
            <Text className="highlight-item">• 保存照片作为饮食记录</Text>
            <Text className="highlight-text">
              照片仅用于个人饮食记录，不会用于其他用途或分享给第三方。
            </Text>
          </View>

          <View className="highlight-box health">
            <Text className="highlight-title">💚 健康数据保护</Text>
            <Text className="highlight-text">
              你的运动、睡眠、饮食等健康数据均加密存储，仅你本人可见，我们承诺：
            </Text>
            <Text className="highlight-item">• 不会出售或出租你的数据</Text>
            <Text className="highlight-item">• 不会用于广告推送</Text>
            <Text className="highlight-item">• 你可以随时删除或导出数据</Text>
          </View>

          <Text className="content-text agreement">
            点击"同意"即表示你已阅读并同意
            <Text className="link-text" onClick={handleViewDetail}>《隐私保护指引》</Text>
            的全部内容。
          </Text>
        </View>

        <View className="modal-footer">
          <Button className="btn-disagree" onClick={onDisagree}>
            不同意
          </Button>
          <Button className="btn-agree" onClick={onAgree}>
            同意
          </Button>
        </View>
      </View>
    </View>
  );
}

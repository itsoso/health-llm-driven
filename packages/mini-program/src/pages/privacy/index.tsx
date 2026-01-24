/**
 * 隐私保护指引页面
 */
import { View, Text, ScrollView } from '@tarojs/components';
import Taro from '@tarojs/taro';
import './index.scss';

export default function PrivacyPage() {
  return (
    <View className="privacy-page">
      <ScrollView scrollY className="privacy-scroll">
        <View className="privacy-content">
          {/* 标题 */}
          <View className="privacy-header">
            <Text className="privacy-title">隐私保护指引</Text>
            <Text className="update-time">更新日期：2026年1月24日</Text>
            <Text className="effective-time">生效日期：2026年1月24日</Text>
          </View>

          {/* 引言 */}
          <View className="privacy-section">
            <Text className="section-content">
              欢迎使用"自由是自律的泡沫"健康管理小程序（以下简称"本小程序"）。我们非常重视用户的隐私保护和个人信息安全。本隐私保护指引旨在向你说明我们如何收集、使用、存储和保护你的个人信息，以及你享有的相关权利。
            </Text>
            <Text className="section-content">
              请你在使用本小程序前，仔细阅读并充分理解本指引。如果你不同意本指引的任何内容，请停止使用本小程序。
            </Text>
          </View>

          {/* 第一部分：信息收集 */}
          <View className="privacy-section">
            <Text className="section-title">一、我们如何收集和使用你的个人信息</Text>
            
            {/* 1.1 照片信息 */}
            <View className="subsection">
              <Text className="subsection-title">1. 照片或视频信息</Text>
              
              <View className="info-item">
                <Text className="info-label">📸 使用场景</Text>
                <Text className="info-value">饮食记录功能</Text>
              </View>

              <View className="info-item">
                <Text className="info-label">🎯 收集目的</Text>
                <Text className="info-value">
                  • 用户在记录每日饮食时，可以拍摄或从相册选择食物照片{'\n'}
                  • 系统通过AI技术识别照片中的食物种类和份量{'\n'}
                  • 自动计算营养成分（热量、蛋白质、碳水化合物、脂肪）{'\n'}
                  • 将照片保存为饮食记录的附件，方便用户回顾饮食历史
                </Text>
              </View>

              <View className="info-item">
                <Text className="info-label">🔒 数据处理</Text>
                <Text className="info-value">
                  • 照片上传到服务器后，仅用于AI分析和个人饮食记录{'\n'}
                  • 照片存储在用户个人账户下，仅用户本人可见{'\n'}
                  • 不会用于其他用途，不会分享给第三方{'\n'}
                  • 用户可以随时删除已上传的照片
                </Text>
              </View>

              <View className="info-item">
                <Text className="info-label">✅ 用户权利</Text>
                <Text className="info-value">
                  • 你可以选择不使用拍照功能，改为手动输入饮食信息{'\n'}
                  • 你可以随时在"饮食记录"页面删除已上传的照片{'\n'}
                  • 删除照片后，相关数据将从服务器永久删除
                </Text>
              </View>
            </View>

            {/* 1.2 健康数据 */}
            <View className="subsection">
              <Text className="subsection-title">2. 健康数据</Text>
              
              <View className="info-item">
                <Text className="info-label">📊 收集内容</Text>
                <Text className="info-value">
                  • 运动数据：步数、运动时长、运动类型、心率等{'\n'}
                  • 睡眠数据：睡眠时长、睡眠质量、深浅睡比例等{'\n'}
                  • 身体数据：身高、体重、体脂率、BMI等{'\n'}
                  • 饮食数据：食物种类、营养成分、用餐时间等{'\n'}
                  • 鼻炎追踪：喷嚏次数、洗鼻记录、症状描述等
                </Text>
              </View>

              <View className="info-item">
                <Text className="info-label">🎯 使用目的</Text>
                <Text className="info-value">
                  • 为你提供个性化的健康分析和建议{'\n'}
                  • 生成健康报告和趋势分析{'\n'}
                  • 提供智能提醒和健康管理服务{'\n'}
                  • 优化产品功能和用户体验
                </Text>
              </View>

              <View className="info-item">
                <Text className="info-label">🔒 数据安全</Text>
                <Text className="info-value">
                  • 所有健康数据均加密存储{'\n'}
                  • 仅用户本人可以查看和管理自己的数据{'\n'}
                  • 不会出售或出租给任何第三方{'\n'}
                  • 采用严格的访问控制和审计机制
                </Text>
              </View>
            </View>

            {/* 1.3 设备信息 */}
            <View className="subsection">
              <Text className="subsection-title">3. 设备信息</Text>
              
              <View className="info-item">
                <Text className="info-label">📱 收集内容</Text>
                <Text className="info-value">
                  • 设备型号、操作系统版本{'\n'}
                  • 网络类型（WiFi/4G/5G）{'\n'}
                  • IP地址、时区设置
                </Text>
              </View>

              <View className="info-item">
                <Text className="info-label">🎯 使用目的</Text>
                <Text className="info-value">
                  • 保障服务的正常运行{'\n'}
                  • 优化产品性能{'\n'}
                  • 进行故障排查和安全防护
                </Text>
              </View>
            </View>

            {/* 1.4 第三方服务 */}
            <View className="subsection">
              <Text className="subsection-title">4. 第三方服务集成</Text>
              
              <View className="info-item">
                <Text className="info-label">🔗 Garmin 数据同步</Text>
                <Text className="info-value">
                  • 如果你选择绑定 Garmin 设备，我们会从 Garmin 获取你的运动和健康数据{'\n'}
                  • 数据同步需要你授权，你可以随时取消授权{'\n'}
                  • 我们遵守 Garmin 的隐私政策和使用条款
                </Text>
              </View>

              <View className="info-item">
                <Text className="info-label">🤖 AI 服务</Text>
                <Text className="info-value">
                  • 我们使用第三方AI服务（如OpenAI）进行食物识别和健康分析{'\n'}
                  • 发送给AI服务的数据经过脱敏处理，不包含个人身份信息{'\n'}
                  • AI分析结果仅用于为你提供个性化建议
                </Text>
              </View>
            </View>
          </View>

          {/* 第二部分：信息存储 */}
          <View className="privacy-section">
            <Text className="section-title">二、我们如何存储你的个人信息</Text>
            
            <View className="info-item">
              <Text className="info-label">📍 存储地点</Text>
              <Text className="info-value">
                你的个人信息存储在中华人民共和国境内的服务器上。
              </Text>
            </View>

            <View className="info-item">
              <Text className="info-label">⏰ 存储期限</Text>
              <Text className="info-value">
                • 账户存续期间：我们会持续保存你的数据{'\n'}
                • 账户注销后：我们会在30天内删除你的所有个人信息{'\n'}
                • 法律要求：某些数据可能需要保留更长时间以满足法律法规要求
              </Text>
            </View>

            <View className="info-item">
              <Text className="info-label">🔐 安全措施</Text>
              <Text className="info-value">
                • 数据传输加密（HTTPS/TLS）{'\n'}
                • 数据存储加密{'\n'}
                • 访问控制和身份认证{'\n'}
                • 定期安全审计和漏洞扫描{'\n'}
                • 灾备和数据恢复机制
              </Text>
            </View>
          </View>

          {/* 第三部分：信息共享 */}
          <View className="privacy-section">
            <Text className="section-title">三、我们如何共享、转让、公开披露你的个人信息</Text>
            
            <View className="info-item">
              <Text className="info-label">🚫 共享原则</Text>
              <Text className="info-value">
                我们不会与任何公司、组织和个人共享你的个人信息，除非：{'\n'}
                • 获得你的明确同意{'\n'}
                • 法律法规规定的情形{'\n'}
                • 与授权合作伙伴共享（如Garmin），且仅限于提供服务所必需
              </Text>
            </View>

            <View className="info-item">
              <Text className="info-label">🔄 转让</Text>
              <Text className="info-value">
                我们不会将你的个人信息转让给任何公司、组织和个人，除非：{'\n'}
                • 获得你的明确同意{'\n'}
                • 涉及合并、收购或破产清算时，我们会要求新的持有方继续受本指引约束
              </Text>
            </View>

            <View className="info-item">
              <Text className="info-label">📢 公开披露</Text>
              <Text className="info-value">
                我们不会公开披露你的个人信息，除非：{'\n'}
                • 获得你的明确同意{'\n'}
                • 法律法规、法律程序、诉讼或政府主管部门强制性要求
              </Text>
            </View>
          </View>

          {/* 第四部分：用户权利 */}
          <View className="privacy-section">
            <Text className="section-title">四、你的权利</Text>
            
            <View className="info-item">
              <Text className="info-label">👁️ 访问权</Text>
              <Text className="info-value">
                你有权访问你的个人信息，可以在"个人设置"页面查看和管理。
              </Text>
            </View>

            <View className="info-item">
              <Text className="info-label">✏️ 更正权</Text>
              <Text className="info-value">
                你有权更正你的个人信息，可以在"个人设置"页面进行修改。
              </Text>
            </View>

            <View className="info-item">
              <Text className="info-label">🗑️ 删除权</Text>
              <Text className="info-value">
                你有权删除你的个人信息，包括：{'\n'}
                • 删除单条饮食记录、运动记录等{'\n'}
                • 删除已上传的照片{'\n'}
                • 注销账户（将删除所有数据）
              </Text>
            </View>

            <View className="info-item">
              <Text className="info-label">🚪 撤回同意权</Text>
              <Text className="info-value">
                你有权撤回授权同意，包括：{'\n'}
                • 取消Garmin数据同步授权{'\n'}
                • 关闭照片访问权限{'\n'}
                • 注销账户
              </Text>
            </View>

            <View className="info-item">
              <Text className="info-label">📤 导出权</Text>
              <Text className="info-value">
                你有权导出你的个人数据，可以联系我们获取数据副本。
              </Text>
            </View>
          </View>

          {/* 第五部分：未成年人保护 */}
          <View className="privacy-section">
            <Text className="section-title">五、未成年人保护</Text>
            
            <Text className="section-content">
              我们非常重视未成年人的个人信息保护。如果你是未成年人，请在监护人的陪同下阅读本指引，并在监护人同意的前提下使用我们的服务。
            </Text>
            <Text className="section-content">
              如果我们发现在未事先获得可证实的监护人同意的情况下收集了未成年人的个人信息，我们会设法尽快删除相关数据。
            </Text>
          </View>

          {/* 第六部分：指引更新 */}
          <View className="privacy-section">
            <Text className="section-title">六、本指引如何更新</Text>
            
            <Text className="section-content">
              我们可能适时修订本指引的条款。当指引发生变更时，我们会在小程序内通过弹窗、公告等形式向你展示变更后的内容。
            </Text>
            <Text className="section-content">
              如果你不同意修改后的内容，你可以选择停止使用我们的服务。如果你继续使用我们的服务，即表示你同意受修订后的指引约束。
            </Text>
          </View>

          {/* 第七部分：联系我们 */}
          <View className="privacy-section">
            <Text className="section-title">七、如何联系我们</Text>
            
            <Text className="section-content">
              如果你对本隐私保护指引有任何疑问、意见或建议，或者需要行使你的权利，请通过以下方式联系我们：
            </Text>

            <View className="contact-info">
              <Text className="contact-item">📧 邮箱：support@executor.life</Text>
              <Text className="contact-item">🌐 网站：https://health.executor.life</Text>
            </View>

            <Text className="section-content">
              我们将在15个工作日内回复你的请求。
            </Text>
          </View>

          {/* 底部 */}
          <View className="privacy-footer">
            <Text className="footer-text">感谢你信任并使用我们的服务！</Text>
          </View>
        </View>
      </ScrollView>
    </View>
  );
}

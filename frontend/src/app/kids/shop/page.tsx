'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useKidsTheme, SKINS } from '@/contexts/KidsThemeContext';

export default function KidsShopPage() {
  const router = useRouter();
  const { theme, points, currentSkinId, unlockedSkins, setSkin, purchaseSkin } = useKidsTheme();
  const [purchasedToast, setPurchasedToast] = useState('');
  const [errorToast, setErrorToast] = useState('');

  const handleAction = (skinId: string, cost: number) => {
    if (unlockedSkins.includes(skinId)) {
      setSkin(skinId);
    } else {
      if (points < cost) {
        setErrorToast(`还差 ${cost - points} 积分`);
        setTimeout(() => setErrorToast(''), 2000);
        return;
      }
      const success = purchaseSkin(skinId);
      if (success) {
        setSkin(skinId);
        const skin = SKINS.find(s => s.id === skinId);
        setPurchasedToast(`🎉 已解锁 ${skin?.name}！`);
        setTimeout(() => setPurchasedToast(''), 2500);
      }
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* 顶栏 */}
      <div className={`px-6 py-4 bg-white/60 backdrop-blur-sm border-b-2 ${theme.navBorder} flex-shrink-0`}>
        <div className="flex items-center justify-between max-w-2xl mx-auto">
          <div className="flex items-center gap-3">
            <button
              onClick={() => router.back()}
              className={`w-10 h-10 rounded-full bg-white border-2 ${theme.navBorder} flex items-center justify-center text-gray-600 active:scale-90 transition-all shadow-sm`}
            >
              ←
            </button>
            <h1 className={`text-2xl font-bold ${theme.accent}`}>🛍️ 皮肤商店</h1>
          </div>
          <div className={`flex items-center gap-1.5 px-4 py-2 rounded-full bg-gradient-to-r ${theme.btnGrad} shadow-md`}>
            <span className="text-lg">⭐</span>
            <span className="text-white font-bold text-lg">{points}</span>
          </div>
        </div>
      </div>

      {/* 积分说明 */}
      <div className="px-6 py-3 bg-white/40">
        <div className="max-w-2xl mx-auto">
          <p className="text-sm text-gray-500 text-center">
            完成计划可获得积分：60%→1分 · 70%→2分 · 80%→3分 · 90%→4分 · 100%→5分
          </p>
        </div>
      </div>

      {/* 皮肤列表 */}
      <div className="flex-1 overflow-y-auto px-4 py-4">
        <div className="max-w-2xl mx-auto grid grid-cols-2 gap-4 pb-4">
          {SKINS.map(skin => {
            const isCurrent = currentSkinId === skin.id;
            const isOwned = unlockedSkins.includes(skin.id);
            const canAfford = points >= skin.cost;

            return (
              <div
                key={skin.id}
                className={`bg-white rounded-2xl shadow-md overflow-hidden transition-all border-2 ${
                  isCurrent ? `${theme.cardBorder} shadow-lg` : 'border-gray-100'
                }`}
              >
                {/* 颜色预览 */}
                <div className={`h-20 bg-gradient-to-br ${skin.btnGrad} flex items-center justify-center relative`}>
                  <span className="text-4xl">{skin.icon}</span>
                  {isCurrent && (
                    <div className="absolute top-2 right-2 bg-white/90 rounded-full px-2 py-0.5 text-xs font-bold text-gray-700">
                      使用中
                    </div>
                  )}
                  {isOwned && !isCurrent && (
                    <div className="absolute top-2 right-2 bg-white/90 rounded-full px-2 py-0.5 text-xs font-bold text-green-600">
                      已拥有
                    </div>
                  )}
                </div>

                {/* 信息 */}
                <div className="p-3">
                  <div className="font-bold text-gray-800 text-base mb-1">{skin.name}</div>
                  <div className="text-sm mb-3">
                    {skin.cost === 0 ? (
                      <span className="text-gray-400">免费</span>
                    ) : (
                      <span className="text-amber-500 font-medium">⭐ {skin.cost} 积分</span>
                    )}
                  </div>

                  {/* 按钮 */}
                  {isCurrent ? (
                    <div className={`w-full py-2 rounded-xl bg-gradient-to-r ${theme.btnGrad} text-white text-sm font-bold text-center opacity-80`}>
                      ✓ 当前使用
                    </div>
                  ) : isOwned ? (
                    <button
                      onClick={() => handleAction(skin.id, skin.cost)}
                      className={`w-full py-2 rounded-xl bg-gradient-to-r ${theme.btnGrad} text-white text-sm font-bold active:scale-95 transition-all shadow-sm`}
                    >
                      切换皮肤
                    </button>
                  ) : canAfford ? (
                    <button
                      onClick={() => handleAction(skin.id, skin.cost)}
                      className={`w-full py-2 rounded-xl bg-gradient-to-r ${theme.btnGrad} text-white text-sm font-bold active:scale-95 transition-all shadow-sm`}
                    >
                      兑换 {skin.cost}pt
                    </button>
                  ) : (
                    <div className="w-full py-2 rounded-xl bg-gray-100 text-gray-400 text-sm font-medium text-center">
                      差 {skin.cost - points} 积分
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* 成功 Toast */}
      {purchasedToast && (
        <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-[300] bg-black/70 text-white px-8 py-5 rounded-2xl text-xl font-bold pointer-events-none text-center">
          {purchasedToast}
        </div>
      )}

      {/* 失败 Toast */}
      {errorToast && (
        <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-[300] bg-red-500/90 text-white px-8 py-4 rounded-2xl text-lg font-bold pointer-events-none text-center">
          {errorToast}
        </div>
      )}
    </div>
  );
}

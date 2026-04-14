'use client';

import { useState, useEffect, useCallback } from 'react';
import { useKidsTheme } from '@/contexts/KidsThemeContext';
import { kidsPetApi, KidsPetState } from '@/services/api/content';

interface Breed {
  id: string;
  name: string;
  image: string;
  cost: number;
  desc: string;
  cardFrom: string;
  cardTo: string;
  glowBg: string;
}

const BREEDS: Breed[] = [
  { id: 'rural', name: '中华田园犬', image: '/kids/dog/breeds/rural.png', cost: 5, desc: '忠实可靠，聪明坚强', cardFrom: 'from-amber-100', cardTo: 'to-orange-100', glowBg: 'bg-amber-50' },
  { id: 'corgi', name: '柯基犬', image: '/kids/dog/breeds/corgi.png', cost: 10, desc: '短腿电动马达，元气满满', cardFrom: 'from-orange-100', cardTo: 'to-amber-100', glowBg: 'bg-orange-50' },
  { id: 'poodle', name: '贵宾犬', image: '/kids/dog/breeds/poodle.png', cost: 15, desc: '聪明优雅，活泼可爱', cardFrom: 'from-pink-100', cardTo: 'to-rose-100', glowBg: 'bg-pink-50' },
  { id: 'shiba', name: '柴犬', image: '/kids/dog/breeds/shiba.png', cost: 18, desc: '治愈笑容，独立可爱', cardFrom: 'from-red-100', cardTo: 'to-orange-100', glowBg: 'bg-red-50' },
  { id: 'border_collie', name: '边境牧羊犬', image: '/kids/dog/breeds/border-collie.png', cost: 20, desc: '高智商运动健将', cardFrom: 'from-slate-100', cardTo: 'to-gray-100', glowBg: 'bg-slate-50' },
  { id: 'husky', name: '哈士奇', image: '/kids/dog/breeds/husky.png', cost: 24, desc: '调皮搞怪，雪地王者', cardFrom: 'from-blue-100', cardTo: 'to-slate-100', glowBg: 'bg-blue-50' },
  { id: 'golden', name: '金毛寻回犬', image: '/kids/dog/breeds/golden.png', cost: 27, desc: '温顺亲人，忠诚可靠', cardFrom: 'from-yellow-100', cardTo: 'to-orange-100', glowBg: 'bg-yellow-50' },
  { id: 'samoyed', name: '萨摩耶', image: '/kids/dog/breeds/samoyed.png', cost: 30, desc: '天使笑容，白色精灵', cardFrom: 'from-sky-50', cardTo: 'to-blue-50', glowBg: 'bg-sky-50' },
];

const XP_PER_LEVEL = 60;

function getBreed(id: string) {
  return BREEDS.find(b => b.id === id) ?? BREEDS[0];
}

function getMood(h: number, hp: number) {
  const v = Math.min(h, hp);
  if (v >= 80) return { emoji: '😄', label: '超级开心！', color: 'text-green-500' };
  if (v >= 60) return { emoji: '😊', label: '心情不错~', color: 'text-green-400' };
  if (v >= 40) return { emoji: '😐', label: '还好啦', color: 'text-yellow-500' };
  if (v >= 20) return { emoji: '😟', label: '有点难过…', color: 'text-orange-500' };
  return { emoji: '😢', label: '又饿又伤心！', color: 'text-red-500' };
}

function Bar({ value }: { value: number }) {
  const color = value >= 60 ? 'from-green-400 to-emerald-400'
    : value >= 35 ? 'from-yellow-400 to-orange-400'
      : 'from-orange-400 to-red-400';
  return (
    <div className="w-full h-3 rounded-full bg-gray-100 overflow-hidden">
      <div className={`h-full rounded-full bg-gradient-to-r ${color} transition-all duration-700`} style={{ width: `${value}%` }} />
    </div>
  );
}

export default function KidsDogPage() {
  const { theme, points, addPoints } = useKidsTheme();
  const [dog, setDog] = useState<KidsPetState | null>(null);
  const [showAdopt, setShowAdopt] = useState(false);
  const [selectedBreed, setSelectedBreed] = useState<Breed | null>(null);
  const [dogName, setDogName] = useState('');
  const [toast, setToast] = useState('');
  const [toastOk, setToastOk] = useState(true);
  const [loading, setLoading] = useState(false);
  const [confirmReturn, setConfirmReturn] = useState<'house' | 'garden' | 'dog' | null>(null);

  const notify = useCallback((msg: string, ok = true) => {
    setToast(msg);
    setToastOk(ok);
    setTimeout(() => setToast(''), 2500);
  }, []);

  const reconcilePoints = useCallback((nextPoints: number) => {
    const delta = nextPoints - points;
    if (delta !== 0) addPoints(delta);
  }, [points, addPoints]);

  const loadPet = useCallback(async () => {
    try {
      const { data } = await kidsPetApi.getMyPet();
      setDog(data.has_pet ? (data.pet || null) : null);
      reconcilePoints(data.kids_points || 0);
    } catch {
      notify('加载狗狗空间失败，请稍后重试', false);
    }
  }, [notify, reconcilePoints]);

  useEffect(() => {
    void loadPet();
  }, [loadPet]);

  const handleAdopt = async () => {
    if (!selectedBreed || !dogName.trim()) return;
    setLoading(true);
    try {
      const { data } = await kidsPetApi.adoptPet({
        breed_id: selectedBreed.id,
        breed_name: selectedBreed.name,
        breed_cost: selectedBreed.cost,
        breed_image: selectedBreed.image,
        dog_name: dogName.trim(),
      });
      setDog(data.pet || null);
      reconcilePoints(data.kids_points || 0);
      setShowAdopt(false);
      setSelectedBreed(null);
      setDogName('');
      notify('🎉 领养成功！');
    } catch (error: any) {
      notify(error?.response?.data?.detail || '领养失败', false);
    } finally {
      setLoading(false);
    }
  };

  const handleAction = async (action: 'buy_food' | 'feed' | 'feed_full' | 'buy_house' | 'buy_garden' | 'return_house' | 'return_garden' | 'return_dog') => {
    if (!dog && action !== 'return_dog') return;
    setLoading(true);
    try {
      const { data } = await kidsPetApi.action(action);
      setDog(data.has_pet ? (data.pet || null) : null);
      reconcilePoints(data.kids_points || 0);
      notify(data.message || '操作成功');
    } catch (error: any) {
      notify(error?.response?.data?.detail || '操作失败', false);
    } finally {
      setLoading(false);
      setConfirmReturn(null);
    }
  };

  const breed = dog ? getBreed(dog.breed_id) : null;
  const mood = dog ? getMood(dog.hunger, dog.happiness) : null;

  if (!dog && !showAdopt) {
    return (
      <div className="flex flex-col items-center justify-center h-full px-6 text-center">
        <div className="text-8xl mb-4 animate-bounce">🐶</div>
        <h1 className={`text-3xl font-bold ${theme.accent} mb-2`}>狗狗空间</h1>
        <p className="text-gray-400 text-lg mb-8">8种品种可领养，状态每日自动衰减，互动消耗积分</p>
        <div className="grid grid-cols-4 gap-3 mb-8 w-full max-w-xs">
          {BREEDS.slice(0, 4).map(b => (
            <div key={b.id} className={`flex flex-col items-center p-2 rounded-2xl bg-gradient-to-br ${b.cardFrom} ${b.cardTo}`}>
              <img src={b.image} alt={b.name} className="w-12 h-12 object-contain" />
              <span className="text-[10px] text-gray-600 font-medium mt-0.5">⭐{b.cost}</span>
            </div>
          ))}
        </div>
        <button
          onClick={() => setShowAdopt(true)}
          className={`w-full max-w-sm py-4 rounded-2xl bg-gradient-to-r ${theme.btnGrad} text-white text-xl font-bold shadow-lg active:scale-95 transition-all`}
        >
          🐾 去领养小狗
        </button>
        {toast && <div className={`fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-[300] ${toastOk ? 'bg-black/70' : 'bg-red-500/90'} text-white px-6 py-4 rounded-2xl text-lg font-bold pointer-events-none`}>{toast}</div>}
      </div>
    );
  }

  if (showAdopt) {
    return (
      <div className="flex flex-col h-full">
        <div className={`px-6 py-4 bg-white/60 backdrop-blur-sm border-b-2 ${theme.navBorder} flex items-center gap-3 flex-shrink-0`}>
          <button onClick={() => { setShowAdopt(false); setSelectedBreed(null); setDogName(''); }} className={`w-10 h-10 rounded-full bg-white border-2 ${theme.navBorder} flex items-center justify-center text-gray-600 active:scale-90 transition-all`}>←</button>
          <h1 className={`text-2xl font-bold ${theme.accent}`}>🐾 领养小狗</h1>
          <div className={`ml-auto flex items-center gap-1 px-3 py-1.5 rounded-full bg-gradient-to-r ${theme.btnGrad}`}>
            <span className="text-white text-sm font-bold">⭐ {points}</span>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto px-4 py-4">
          <p className="text-center text-gray-400 text-sm mb-4">从中华田园犬到萨摩耶，选择你的伙伴</p>
          <div className="grid grid-cols-2 gap-4 max-w-xl mx-auto">
            {BREEDS.map(b => {
              const canAfford = points >= b.cost;
              return (
                <div key={b.id} className={`rounded-2xl overflow-hidden shadow-md border-2 ${canAfford ? 'border-gray-100' : 'border-gray-100 opacity-70'}`}>
                  <div className={`h-24 bg-gradient-to-br ${b.cardFrom} ${b.cardTo} flex items-center justify-center`}>
                    <img src={b.image} alt={b.name} className="w-16 h-16 object-contain" />
                  </div>
                  <div className="p-3 bg-white">
                    <div className="font-bold text-gray-800 mb-0.5">{b.name}</div>
                    <div className="text-xs text-gray-500 mb-2">{b.desc}</div>
                    <div className="text-amber-500 text-sm font-bold mb-2">⭐ {b.cost} 积分</div>
                    {canAfford ? (
                      <button onClick={() => setSelectedBreed(b)} className={`w-full py-2 rounded-xl bg-gradient-to-r ${theme.btnGrad} text-white text-sm font-bold active:scale-95 transition-all disabled:opacity-60`} disabled={loading}>
                        领养 TA
                      </button>
                    ) : (
                      <div className="w-full py-2 rounded-xl bg-gray-100 text-gray-400 text-sm font-medium text-center">差 {b.cost - points} 积分</div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
        {selectedBreed && (
          <div className="fixed inset-0 z-[200] flex items-end sm:items-center justify-center bg-black/30">
            <div className="bg-white rounded-t-3xl sm:rounded-3xl p-6 w-full sm:max-w-sm shadow-2xl">
              <div className={`w-20 h-20 rounded-full bg-gradient-to-br ${selectedBreed.cardFrom} ${selectedBreed.cardTo} flex items-center justify-center mx-auto mb-3`}>
                <img src={selectedBreed.image} alt={selectedBreed.name} className="w-14 h-14 object-contain" />
              </div>
              <h3 className={`text-2xl font-bold ${theme.accent} text-center mb-1`}>{selectedBreed.name}</h3>
              <p className="text-gray-400 text-center text-sm mb-5">给你的小狗取个名字吧~</p>
              <input
                type="text"
                value={dogName}
                onChange={e => setDogName(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && !e.nativeEvent.isComposing) void handleAdopt(); }}
                placeholder="比如：小白、球球"
                className={`w-full px-4 py-3 border-2 ${theme.inputBorder} rounded-2xl text-xl text-gray-800 text-center placeholder-gray-400 focus:outline-none ${theme.inputFocus} mb-5`}
                autoFocus
                maxLength={8}
              />
              <div className="flex gap-3">
                <button onClick={() => { setSelectedBreed(null); setDogName(''); }} className="flex-1 py-3 rounded-2xl border-2 border-gray-200 text-lg font-bold text-gray-500 active:scale-95 transition-all">取消</button>
                <button onClick={() => void handleAdopt()} disabled={!dogName.trim() || loading} className={`flex-1 py-3 rounded-2xl bg-gradient-to-r ${theme.btnGrad} text-white text-lg font-bold shadow-md disabled:opacity-40 active:scale-95 transition-all`}>
                  领养（{selectedBreed.cost}分）
                </button>
              </div>
            </div>
          </div>
        )}
        {toast && <div className={`fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-[300] ${toastOk ? 'bg-black/70' : 'bg-red-500/90'} text-white px-6 py-4 rounded-2xl text-lg font-bold pointer-events-none`}>{toast}</div>}
      </div>
    );
  }

  if (!dog || !breed || !mood) return null;
  const levelStars = '⭐'.repeat(Math.min(dog.level, 5));

  return (
    <div className="flex flex-col h-full">
      <div className={`px-6 py-3 bg-white/60 backdrop-blur-sm border-b-2 ${theme.navBorder} flex items-center justify-between flex-shrink-0`}>
        <h1 className={`text-xl font-bold ${theme.accent}`}>🐾 我的小狗</h1>
        <div className={`flex items-center gap-1 px-3 py-1.5 rounded-full bg-gradient-to-r ${theme.btnGrad}`}>
          <span className="text-white text-sm font-bold">⭐ {points}</span>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto">
        <div className={`mx-4 mt-4 rounded-3xl ${breed.glowBg} border-2 border-white shadow-lg p-5 flex flex-col items-center`}>
          <div className="flex items-end justify-center gap-4 mb-3">
            {dog.has_house && <img src="/kids/dog/items/house.png" alt="小屋" className="w-10 h-10 object-contain" />}
            <img src={breed.image} alt={breed.name} className={`w-32 h-32 object-contain ${mood.emoji === '😄' ? 'animate-bounce' : mood.emoji === '😢' ? 'opacity-70' : ''}`} />
            {dog.has_garden && <img src="/kids/dog/items/garden.png" alt="花园" className="w-10 h-10 object-contain" />}
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold text-gray-800">{dog.dog_name}</p>
            <p className="text-sm text-gray-500">{breed.name} · Lv.{dog.level} {levelStars}</p>
            <p className={`text-lg font-bold mt-1 ${mood.color}`}>{mood.emoji} {mood.label}</p>
          </div>
        </div>
        <div className="mx-4 mt-3 p-4 bg-white rounded-2xl shadow-sm border border-gray-100 space-y-3">
          <div>
            <div className="flex justify-between text-sm mb-1"><span className="font-bold text-gray-600">🍖 饥饿值</span><span className="text-gray-500">{dog.hunger}%</span></div>
            <Bar value={dog.hunger} />
          </div>
          <div>
            <div className="flex justify-between text-sm mb-1"><span className="font-bold text-gray-600">❤️ 快乐值</span><span className="text-gray-500">{dog.happiness}%</span></div>
            <Bar value={dog.happiness} />
          </div>
          <div className="text-xs text-gray-400 text-center pt-1">库存：{dog.food_bags} 袋狗粮 · 经验 {dog.xp % XP_PER_LEVEL}/{XP_PER_LEVEL}</div>
        </div>
        <div className="mx-4 mt-3 mb-4">
          <div className="grid grid-cols-2 gap-3">
            <button onClick={() => void handleAction('feed')} disabled={dog.food_bags <= 0 || loading} className={`flex flex-col items-center py-4 rounded-2xl bg-white border-2 ${theme.cardBorder} shadow-sm transition-all active:scale-95 disabled:opacity-40`}>
              <img src="/kids/dog/items/feed-bowl.png" alt="喂食" className="w-10 h-10 mb-1 object-contain" />
              <span className="text-base font-bold text-gray-700">用狗粮喂食</span>
              <span className="text-xs text-gray-400">库存 {dog.food_bags} 袋</span>
            </button>
            <button onClick={() => void handleAction('buy_food')} disabled={loading} className={`flex flex-col items-center py-4 rounded-2xl bg-white border-2 ${theme.cardBorder} shadow-sm transition-all active:scale-95 disabled:opacity-40`}>
              <img src="/kids/dog/items/dog-food.png" alt="狗粮" className="w-10 h-10 mb-1 object-contain" />
              <span className="text-base font-bold text-gray-700">购买狗粮</span>
              <span className="text-xs text-amber-500 font-bold">⭐ 1积分/袋</span>
            </button>
            <button onClick={() => void handleAction('feed_full')} disabled={loading} className={`flex flex-col items-center py-4 rounded-2xl bg-white border-2 ${theme.cardBorder} shadow-sm transition-all active:scale-95 disabled:opacity-40`}>
              <img src="/kids/dog/items/feed-full.png" alt="喂饱" className="w-10 h-10 mb-1 object-contain" />
              <span className="text-base font-bold text-gray-700">直接喂饱</span>
              <span className="text-xs text-amber-500 font-bold">⭐ 2积分</span>
            </button>
            <button onClick={() => dog.has_house ? setConfirmReturn('house') : void handleAction('buy_house')} disabled={loading} className={`flex flex-col items-center py-4 rounded-2xl shadow-sm transition-all active:scale-95 border-2 ${dog.has_house ? 'bg-green-50 border-green-200' : `bg-white ${theme.cardBorder}`} disabled:opacity-40`}>
              <img src="/kids/dog/items/house.png" alt="小屋" className="w-10 h-10 mb-1 object-contain" />
              <span className="text-base font-bold text-gray-700">狗狗小屋</span>
              {dog.has_house ? <span className="text-xs text-orange-500 font-bold">退还 +3积分</span> : <span className="text-xs text-amber-500 font-bold">⭐ 3积分</span>}
            </button>
            <button onClick={() => dog.has_garden ? setConfirmReturn('garden') : void handleAction('buy_garden')} disabled={loading} className={`flex flex-col items-center py-4 rounded-2xl shadow-sm transition-all active:scale-95 border-2 ${dog.has_garden ? 'bg-green-50 border-green-200' : `bg-white ${theme.cardBorder}`} disabled:opacity-40`}>
              <img src="/kids/dog/items/garden.png" alt="花园" className="w-10 h-10 mb-1 object-contain" />
              <span className="text-base font-bold text-gray-700">狗狗花园</span>
              {dog.has_garden ? <span className="text-xs text-orange-500 font-bold">退还 +5积分</span> : <span className="text-xs text-amber-500 font-bold">⭐ 5积分</span>}
            </button>
            <button onClick={() => setConfirmReturn('dog')} disabled={loading} className="col-span-2 flex flex-col items-center py-3 rounded-2xl shadow-sm transition-all active:scale-95 border-2 border-red-100 bg-red-50 disabled:opacity-40">
              <span className="text-base font-bold text-red-400">送走{dog.dog_name}</span>
              <span className="text-xs text-red-300">退还领养积分 +{dog.breed_cost || '?'}</span>
            </button>
          </div>
        </div>
      </div>
      {confirmReturn && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/30">
          <div className="bg-white rounded-3xl p-6 w-[85%] max-w-sm shadow-2xl text-center">
            <div className="text-5xl mb-3">
              {confirmReturn === 'house' ? '🏠' : confirmReturn === 'garden' ? '🌻' : '🐶'}
            </div>
            <h3 className="text-xl font-bold text-gray-800 mb-2">
              {confirmReturn === 'house' ? '确定退还小屋？' : confirmReturn === 'garden' ? '确定退还花园？' : `确定送走${dog.dog_name}？`}
            </h3>
            <p className="text-gray-500 text-sm mb-1">
              {confirmReturn === 'house' ? '退还后将返还 3 积分'
                : confirmReturn === 'garden' ? '退还后将返还 5 积分'
                  : `送走后将返还 ${dog.breed_cost || 0} 积分`}
            </p>
            {confirmReturn === 'dog' && <p className="text-red-400 text-xs mb-4">小屋、花园和狗粮也会一起清除</p>}
            <div className="flex gap-3 mt-4">
              <button onClick={() => setConfirmReturn(null)} className="flex-1 py-3 rounded-2xl border-2 border-gray-200 text-lg font-bold text-gray-500 active:scale-95 transition-all">取消</button>
              <button
                onClick={() => void handleAction(confirmReturn === 'house' ? 'return_house' : confirmReturn === 'garden' ? 'return_garden' : 'return_dog')}
                disabled={loading}
                className="flex-1 py-3 rounded-2xl bg-red-500 text-white text-lg font-bold shadow-md disabled:opacity-40 active:scale-95 transition-all"
              >
                确定
              </button>
            </div>
          </div>
        </div>
      )}
      {toast && <div className={`fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-[300] ${toastOk ? 'bg-black/70' : 'bg-red-500/90'} text-white px-6 py-4 rounded-2xl text-lg font-bold pointer-events-none text-center max-w-xs`}>{toast}</div>}
    </div>
  );
}

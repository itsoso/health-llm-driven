'use client';

import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useKidsTheme } from '@/contexts/KidsThemeContext';

interface DogState {
  breedId: string;
  name: string;
  adoptedAt: string;
  lastVisit: string;
  hunger: number;      // 0–100
  happiness: number;   // 0–100
  level: number;
  xp: number;
  foodBags: number;
  hasHouse: boolean;
  hasGarden: boolean;
}

interface Breed {
  id: string;
  name: string;
  emoji: string;
  cost: number;
  desc: string;
  cardFrom: string;
  cardTo: string;
  glowBg: string;
}

const BREEDS: Breed[] = [
  { id: 'rural',       name: '中华田园犬', emoji: '🐕',   cost: 5,  desc: '忠实可靠，聪明坚强', cardFrom: 'from-amber-100',  cardTo: 'to-orange-100', glowBg: 'bg-amber-50'  },
  { id: 'poodle',      name: '贵宾犬',    emoji: '🐩',   cost: 10, desc: '聪明优雅，活泼可爱', cardFrom: 'from-pink-100',   cardTo: 'to-rose-100',   glowBg: 'bg-pink-50'   },
  { id: 'border_bw',   name: '黑白边牧',  emoji: '🐕‍🦺', cost: 15, desc: '经典黑白，敏捷灵活', cardFrom: 'from-slate-100',  cardTo: 'to-gray-100',   glowBg: 'bg-slate-50'  },
  { id: 'border_lilac',name: '丁香边牧',  emoji: '🐕‍🦺', cost: 15, desc: '罕见淡紫，灵动秀气', cardFrom: 'from-purple-100', cardTo: 'to-violet-100', glowBg: 'bg-purple-50' },
  { id: 'border_gold', name: '金边边牧',  emoji: '🐕‍🦺', cost: 20, desc: '金色镶边，珍贵稀有', cardFrom: 'from-yellow-100', cardTo: 'to-amber-100',  glowBg: 'bg-yellow-50' },
  { id: 'husky',       name: '哈士奇',   emoji: '🐺',   cost: 20, desc: '调皮捣蛋，雪橇小王子', cardFrom: 'from-blue-100',   cardTo: 'to-slate-100',  glowBg: 'bg-blue-50'   },
  { id: 'golden',      name: '金毛寻回犬', emoji: '🦮',  cost: 25, desc: '温顺亲人，忠诚可靠', cardFrom: 'from-yellow-100', cardTo: 'to-orange-100', glowBg: 'bg-orange-50' },
  { id: 'samoyed',     name: '萨摩耶',   emoji: '🐶',   cost: 30, desc: '天使笑容，白色精灵', cardFrom: 'from-sky-50',     cardTo: 'to-blue-50',    glowBg: 'bg-sky-50'    },
];

const HUNGER_DECAY = 20;
const HAPPY_DECAY = 10;
const XP_PER_LEVEL = 60;

function getBreed(id: string) { return BREEDS.find(b => b.id === id) ?? BREEDS[0]; }

function getMood(h: number, hp: number) {
  const v = Math.min(h, hp);
  if (v >= 80) return { emoji: '😄', label: '超级开心！', color: 'text-green-500' };
  if (v >= 60) return { emoji: '😊', label: '心情不错~',  color: 'text-green-400' };
  if (v >= 40) return { emoji: '😐', label: '还好啦',     color: 'text-yellow-500' };
  if (v >= 20) return { emoji: '😟', label: '有点难过…',  color: 'text-orange-500' };
  return         { emoji: '😢', label: '又饿又伤心！', color: 'text-red-500' };
}

function Bar({ value, high }: { value: number; high?: boolean }) {
  const color = value >= 60 ? 'from-green-400 to-emerald-400'
    : value >= 35 ? 'from-yellow-400 to-orange-400'
    : 'from-orange-400 to-red-400';
  return (
    <div className={`w-full h-3 rounded-full ${high ? 'bg-gray-100' : 'bg-gray-100'} overflow-hidden`}>
      <div className={`h-full rounded-full bg-gradient-to-r ${color} transition-all duration-700`} style={{ width: `${value}%` }} />
    </div>
  );
}

export default function KidsDogPage() {
  const { user } = useAuth();
  const { theme, points, addPoints } = useKidsTheme();
  const userId = user?.id || 'guest';
  const dogKey = `kids_dog_${userId}`;

  const [dog, setDog] = useState<DogState | null>(null);
  const [showAdopt, setShowAdopt] = useState(false);
  const [selectedBreed, setSelectedBreed] = useState<Breed | null>(null);
  const [dogName, setDogName] = useState('');
  const [toast, setToast] = useState('');
  const [toastOk, setToastOk] = useState(true);

  const notify = useCallback((msg: string, ok = true) => {
    setToast(msg); setToastOk(ok);
    setTimeout(() => setToast(''), 2500);
  }, []);

  const saveDog = useCallback((d: DogState | null) => {
    if (d) localStorage.setItem(dogKey, JSON.stringify(d));
    else localStorage.removeItem(dogKey);
    setDog(d);
  }, [dogKey]);

  const spend = useCallback((cost: number, label?: string): boolean => {
    if (points < cost) { notify(`积分不足，需要 ${cost} 积分${label ? '买' + label : ''}`, false); return false; }
    addPoints(-cost);
    return true;
  }, [points, addPoints, notify]);

  // Load dog + apply daily decay
  useEffect(() => {
    const raw = localStorage.getItem(dogKey);
    if (!raw) return;
    try {
      const d = JSON.parse(raw) as DogState;
      const days = Math.max(0, Math.floor((Date.now() - new Date(d.lastVisit ?? d.adoptedAt).getTime()) / 86400000));
      if (days > 0) {
        d.hunger    = Math.max(0, d.hunger - days * HUNGER_DECAY);
        if (d.hunger < 50) d.happiness = Math.max(0, d.happiness - days * HAPPY_DECAY);
        d.lastVisit = new Date().toISOString();
        localStorage.setItem(dogKey, JSON.stringify(d));
      }
      setDog(d);
    } catch { /* ignore */ }
  }, [dogKey]);

  /* ─── Actions ─── */
  const handleAdopt = () => {
    if (!selectedBreed || !dogName.trim()) return;
    if (!spend(selectedBreed.cost, selectedBreed.name)) return;
    const now = new Date().toISOString();
    saveDog({ breedId: selectedBreed.id, name: dogName.trim(), adoptedAt: now, lastVisit: now, hunger: 100, happiness: 100, level: 1, xp: 0, foodBags: 0, hasHouse: false, hasGarden: false });
    setShowAdopt(false); setSelectedBreed(null); setDogName('');
    notify(`🎉 ${dogName.trim()} 成功领养！好好爱护它吧~`);
  };

  const feedBag = () => {
    if (!dog) return;
    if (dog.foodBags <= 0) { notify('没有狗粮了，快去买！', false); return; }
    const xp = dog.xp + 5;
    saveDog({ ...dog, hunger: Math.min(100, dog.hunger + 50), happiness: Math.min(100, dog.happiness + 10), foodBags: dog.foodBags - 1, xp, level: Math.floor(xp / XP_PER_LEVEL) + 1, lastVisit: new Date().toISOString() });
    notify('🍖 喂食成功！小狗好满足~');
  };

  const feedFull = () => {
    if (!dog || !spend(2, '喂饱')) return;
    const xp = dog.xp + 12;
    saveDog({ ...dog, hunger: 100, happiness: Math.min(100, dog.happiness + 25), xp, level: Math.floor(xp / XP_PER_LEVEL) + 1, lastVisit: new Date().toISOString() });
    notify('🍖🍖 喂饱啦！小狗超开心！');
  };

  const buyFood = () => {
    if (!dog || !spend(1, '狗粮')) return;
    saveDog({ ...dog, foodBags: dog.foodBags + 1 });
    notify('🛒 购买成功！+1袋狗粮');
  };

  const playWith = () => {
    if (!dog || !spend(1, '玩耍')) return;
    const xp = dog.xp + 8;
    saveDog({ ...dog, happiness: Math.min(100, dog.happiness + 30), xp, level: Math.floor(xp / XP_PER_LEVEL) + 1, lastVisit: new Date().toISOString() });
    notify('🎾 玩耍成功！小狗乐翻了！');
  };

  const buyHouse = () => {
    if (!dog) return;
    if (dog.hasHouse) { notify('已经有小屋啦！', false); return; }
    if (!spend(3, '小屋')) return;
    saveDog({ ...dog, hasHouse: true });
    notify('🏡 小狗有自己的小屋啦！');
  };

  const buyGarden = () => {
    if (!dog) return;
    if (dog.hasGarden) { notify('已经有花园啦！', false); return; }
    if (!spend(5, '花园')) return;
    saveDog({ ...dog, hasGarden: true });
    notify('🌸 小狗有专属花园啦！');
  };

  /* ─── Render helpers ─── */
  const breed = dog ? getBreed(dog.breedId) : null;
  const mood = dog ? getMood(dog.hunger, dog.happiness) : null;

  /* ─── No dog: CTA ─── */
  if (!dog && !showAdopt) return (
    <div className="flex flex-col items-center justify-center h-full px-6 text-center">
      <div className="text-8xl mb-4 animate-bounce">🐶</div>
      <h1 className={`text-3xl font-bold ${theme.accent} mb-2`}>狗狗空间</h1>
      <p className="text-gray-400 text-lg mb-8">完成每日计划和打卡<br/>积累积分，领养自己的小狗！</p>
      <div className="grid grid-cols-4 gap-3 mb-8 w-full max-w-xs">
        {BREEDS.slice(0, 4).map(b => (
          <div key={b.id} className={`flex flex-col items-center p-2 rounded-2xl bg-gradient-to-br ${b.cardFrom} ${b.cardTo}`}>
            <span className="text-3xl">{b.emoji}</span>
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
      {/* Toast */}
      {toast && <div className={`fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-[300] ${toastOk ? 'bg-black/70' : 'bg-red-500/90'} text-white px-6 py-4 rounded-2xl text-lg font-bold pointer-events-none`}>{toast}</div>}
    </div>
  );

  /* ─── Adopt: breed selection ─── */
  if (showAdopt) return (
    <div className="flex flex-col h-full">
      <div className={`px-6 py-4 bg-white/60 backdrop-blur-sm border-b-2 ${theme.navBorder} flex items-center gap-3 flex-shrink-0`}>
        <button onClick={() => { setShowAdopt(false); setSelectedBreed(null); setDogName(''); }}
          className={`w-10 h-10 rounded-full bg-white border-2 ${theme.navBorder} flex items-center justify-center text-gray-600 active:scale-90 transition-all`}>←</button>
        <h1 className={`text-2xl font-bold ${theme.accent}`}>🐾 领养小狗</h1>
        <div className={`ml-auto flex items-center gap-1 px-3 py-1.5 rounded-full bg-gradient-to-r ${theme.btnGrad}`}>
          <span className="text-white text-sm font-bold">⭐ {points}</span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4">
        <p className="text-center text-gray-400 text-sm mb-4">选择你喜欢的品种，完成计划积累积分来领养</p>
        <div className="grid grid-cols-2 gap-4 max-w-xl mx-auto">
          {BREEDS.map(b => {
            const canAfford = points >= b.cost;
            return (
              <div key={b.id} className={`rounded-2xl overflow-hidden shadow-md border-2 ${canAfford ? 'border-gray-100' : 'border-gray-100 opacity-70'}`}>
                <div className={`h-24 bg-gradient-to-br ${b.cardFrom} ${b.cardTo} flex items-center justify-center`}>
                  <span className="text-6xl">{b.emoji}</span>
                </div>
                <div className="p-3 bg-white">
                  <div className="font-bold text-gray-800 mb-0.5">{b.name}</div>
                  <div className="text-xs text-gray-500 mb-2">{b.desc}</div>
                  <div className="text-amber-500 text-sm font-bold mb-2">⭐ {b.cost} 积分</div>
                  {canAfford ? (
                    <button onClick={() => setSelectedBreed(b)}
                      className={`w-full py-2 rounded-xl bg-gradient-to-r ${theme.btnGrad} text-white text-sm font-bold active:scale-95 transition-all`}>
                      领养 TA
                    </button>
                  ) : (
                    <div className="w-full py-2 rounded-xl bg-gray-100 text-gray-400 text-sm font-medium text-center">
                      差 {b.cost - points} 积分
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Naming modal */}
      {selectedBreed && (
        <div className="fixed inset-0 z-[200] flex items-end sm:items-center justify-center bg-black/30">
          <div className="bg-white rounded-t-3xl sm:rounded-3xl p-6 w-full sm:max-w-sm shadow-2xl">
            <div className={`w-20 h-20 rounded-full bg-gradient-to-br ${selectedBreed.cardFrom} ${selectedBreed.cardTo} flex items-center justify-center mx-auto mb-3`}>
              <span className="text-5xl">{selectedBreed.emoji}</span>
            </div>
            <h3 className={`text-2xl font-bold ${theme.accent} text-center mb-1`}>{selectedBreed.name}</h3>
            <p className="text-gray-400 text-center text-sm mb-5">给你的小狗取个名字吧~</p>
            <input
              type="text"
              value={dogName}
              onChange={e => setDogName(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !e.nativeEvent.isComposing) handleAdopt(); }}
              placeholder="比如：小白、球球"
              className={`w-full px-4 py-3 border-2 ${theme.inputBorder} rounded-2xl text-xl text-gray-800 text-center placeholder-gray-400 focus:outline-none ${theme.inputFocus} mb-5`}
              autoFocus maxLength={8}
            />
            <div className="flex gap-3">
              <button onClick={() => { setSelectedBreed(null); setDogName(''); }}
                className="flex-1 py-3 rounded-2xl border-2 border-gray-200 text-lg font-bold text-gray-500 active:scale-95 transition-all">取消</button>
              <button onClick={handleAdopt} disabled={!dogName.trim()}
                className={`flex-1 py-3 rounded-2xl bg-gradient-to-r ${theme.btnGrad} text-white text-lg font-bold shadow-md disabled:opacity-40 active:scale-95 transition-all`}>
                领养（{selectedBreed.cost}分）
              </button>
            </div>
          </div>
        </div>
      )}

      {toast && <div className={`fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-[300] ${toastOk ? 'bg-black/70' : 'bg-red-500/90'} text-white px-6 py-4 rounded-2xl text-lg font-bold pointer-events-none`}>{toast}</div>}
    </div>
  );

  /* ─── Care screen ─── */
  if (!dog || !breed || !mood) return null;

  const levelStars = '⭐'.repeat(Math.min(dog.level, 5));

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className={`px-6 py-3 bg-white/60 backdrop-blur-sm border-b-2 ${theme.navBorder} flex items-center justify-between flex-shrink-0`}>
        <h1 className={`text-xl font-bold ${theme.accent}`}>🐾 我的小狗</h1>
        <div className="flex items-center gap-3">
          <button onClick={() => setShowAdopt(true)} className="text-sm text-gray-400 underline">换一只</button>
          <div className={`flex items-center gap-1 px-3 py-1.5 rounded-full bg-gradient-to-r ${theme.btnGrad}`}>
            <span className="text-white text-sm font-bold">⭐ {points}</span>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {/* Dog display */}
        <div className={`mx-4 mt-4 rounded-3xl ${breed.glowBg} border-2 border-white shadow-lg p-5 flex flex-col items-center`}>
          <div className="flex items-end justify-center gap-4 mb-3">
            {dog.hasHouse && <div className="text-4xl">🏡</div>}
            <div className={`text-8xl ${mood.emoji === '😄' ? 'animate-bounce' : mood.emoji === '😢' ? 'opacity-70' : ''}`}>
              {breed.emoji}
            </div>
            {dog.hasGarden && <div className="text-4xl">🌸</div>}
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold text-gray-800">{dog.name}</p>
            <p className="text-sm text-gray-500">{breed.name} · Lv.{dog.level} {levelStars}</p>
            <p className={`text-lg font-bold mt-1 ${mood.color}`}>{mood.emoji} {mood.label}</p>
          </div>
        </div>

        {/* Status bars */}
        <div className="mx-4 mt-3 p-4 bg-white rounded-2xl shadow-sm border border-gray-100 space-y-3">
          <div>
            <div className="flex justify-between text-sm mb-1">
              <span className="font-bold text-gray-600">🍖 饥饿值</span>
              <span className="text-gray-500">{dog.hunger}%</span>
            </div>
            <Bar value={dog.hunger} />
          </div>
          <div>
            <div className="flex justify-between text-sm mb-1">
              <span className="font-bold text-gray-600">❤️ 快乐值</span>
              <span className="text-gray-500">{dog.happiness}%</span>
            </div>
            <Bar value={dog.happiness} />
          </div>
          <div className="text-xs text-gray-400 text-center pt-1">
            库存：{dog.foodBags} 袋狗粮 · 经验 {dog.xp % XP_PER_LEVEL}/{XP_PER_LEVEL}
          </div>
        </div>

        {/* Actions */}
        <div className="mx-4 mt-3 mb-4">
          <div className="grid grid-cols-2 gap-3">
            {/* Feed with bag */}
            <button onClick={feedBag} disabled={dog.foodBags <= 0}
              className={`flex flex-col items-center py-4 rounded-2xl bg-white border-2 ${theme.cardBorder} shadow-sm transition-all active:scale-95 disabled:opacity-40`}>
              <span className="text-3xl mb-1">🍖</span>
              <span className="text-base font-bold text-gray-700">用狗粮喂食</span>
              <span className="text-xs text-gray-400">库存 {dog.foodBags} 袋</span>
            </button>

            {/* Buy food */}
            <button onClick={buyFood}
              className={`flex flex-col items-center py-4 rounded-2xl bg-white border-2 ${theme.cardBorder} shadow-sm transition-all active:scale-95`}>
              <span className="text-3xl mb-1">🛒</span>
              <span className="text-base font-bold text-gray-700">购买狗粮</span>
              <span className="text-xs text-amber-500 font-bold">⭐ 1积分/袋</span>
            </button>

            {/* Feed full */}
            <button onClick={feedFull}
              className={`flex flex-col items-center py-4 rounded-2xl bg-white border-2 ${theme.cardBorder} shadow-sm transition-all active:scale-95`}>
              <span className="text-3xl mb-1">🍖🍖</span>
              <span className="text-base font-bold text-gray-700">直接喂饱</span>
              <span className="text-xs text-amber-500 font-bold">⭐ 2积分</span>
            </button>

            {/* Play */}
            <button onClick={playWith}
              className={`flex flex-col items-center py-4 rounded-2xl bg-white border-2 ${theme.cardBorder} shadow-sm transition-all active:scale-95`}>
              <span className="text-3xl mb-1">🎾</span>
              <span className="text-base font-bold text-gray-700">陪狗玩耍</span>
              <span className="text-xs text-amber-500 font-bold">⭐ 1积分</span>
            </button>

            {/* House */}
            <button onClick={buyHouse} disabled={dog.hasHouse}
              className={`flex flex-col items-center py-4 rounded-2xl shadow-sm transition-all active:scale-95 border-2 ${dog.hasHouse ? 'bg-green-50 border-green-200' : `bg-white ${theme.cardBorder}`}`}>
              <span className="text-3xl mb-1">🏡</span>
              <span className="text-base font-bold text-gray-700">狗狗小屋</span>
              {dog.hasHouse
                ? <span className="text-xs text-green-500 font-bold">✓ 已拥有</span>
                : <span className="text-xs text-amber-500 font-bold">⭐ 3积分</span>}
            </button>

            {/* Garden */}
            <button onClick={buyGarden} disabled={dog.hasGarden}
              className={`flex flex-col items-center py-4 rounded-2xl shadow-sm transition-all active:scale-95 border-2 ${dog.hasGarden ? 'bg-green-50 border-green-200' : `bg-white ${theme.cardBorder}`}`}>
              <span className="text-3xl mb-1">🌸</span>
              <span className="text-base font-bold text-gray-700">狗狗花园</span>
              {dog.hasGarden
                ? <span className="text-xs text-green-500 font-bold">✓ 已拥有</span>
                : <span className="text-xs text-amber-500 font-bold">⭐ 5积分</span>}
            </button>
          </div>
        </div>
      </div>

      {/* Naming modal when "换一只" */}
      {showAdopt && !dog && null}

      {toast && (
        <div className={`fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-[300] ${toastOk ? 'bg-black/70' : 'bg-red-500/90'} text-white px-6 py-4 rounded-2xl text-lg font-bold pointer-events-none text-center max-w-xs`}>
          {toast}
        </div>
      )}
    </div>
  );
}

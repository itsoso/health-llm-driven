'use client';

import { useState, useEffect, useCallback, createContext, useContext, ReactNode } from 'react';

interface UnlockedBadge {
  name: string;
  icon: string;
}

interface CelebrationContextType {
  celebrate: (badges: UnlockedBadge[]) => void;
}

const CelebrationContext = createContext<CelebrationContextType | undefined>(undefined);

export function useCelebration() {
  const ctx = useContext(CelebrationContext);
  if (!ctx) throw new Error('useCelebration must be used within CelebrationProvider');
  return ctx;
}

function Particle({ delay, left }: { delay: number; left: number }) {
  const colors = ['#FFD700', '#FF6B6B', '#4ECDC4', '#A78BFA', '#F97316', '#60A5FA'];
  const color = colors[Math.floor(Math.random() * colors.length)];
  const size = 4 + Math.random() * 8;

  return (
    <div
      className="absolute rounded-full animate-confetti"
      style={{
        left: `${left}%`,
        top: '-10px',
        width: size,
        height: size,
        backgroundColor: color,
        animationDelay: `${delay}ms`,
        animationDuration: `${1500 + Math.random() * 1000}ms`,
      }}
    />
  );
}

function CelebrationOverlay({ badges, onClose }: { badges: UnlockedBadge[]; onClose: () => void }) {
  const [visible, setVisible] = useState(false);
  const [currentIndex, setCurrentIndex] = useState(0);

  useEffect(() => {
    requestAnimationFrame(() => setVisible(true));
    const timer = setTimeout(() => {
      if (currentIndex < badges.length - 1) {
        setCurrentIndex(prev => prev + 1);
      } else {
        onClose();
      }
    }, 3000);
    return () => clearTimeout(timer);
  }, [currentIndex, badges.length, onClose]);

  const badge = badges[currentIndex];

  return (
    <div
      className={`fixed inset-0 z-[200] flex items-center justify-center transition-all duration-500 ${
        visible ? 'bg-black/50 backdrop-blur-sm' : 'bg-transparent'
      }`}
      onClick={onClose}
    >
      {/* Particles */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        {Array.from({ length: 30 }).map((_, i) => (
          <Particle key={i} delay={i * 80} left={Math.random() * 100} />
        ))}
      </div>

      {/* Badge card */}
      <div
        className={`relative bg-white rounded-3xl p-8 max-w-sm w-full mx-4 shadow-2xl transform transition-all duration-700 ${
          visible ? 'scale-100 opacity-100 translate-y-0' : 'scale-50 opacity-0 translate-y-10'
        }`}
        onClick={e => e.stopPropagation()}
      >
        {/* Glow ring */}
        <div className="absolute inset-0 rounded-3xl bg-gradient-to-r from-yellow-400 via-purple-500 to-pink-500 opacity-20 blur-xl animate-pulse" />

        <div className="relative text-center">
          {/* Badge icon */}
          <div className="relative inline-block">
            <span className="text-7xl block animate-bounce-badge">{badge.icon}</span>
            <div className="absolute inset-0 animate-ping-slow opacity-30">
              <span className="text-7xl block">{badge.icon}</span>
            </div>
          </div>

          {/* Title */}
          <h2 className="text-2xl font-bold text-gray-800 mt-4 animate-fade-up">
            成就解锁!
          </h2>

          {/* Badge name */}
          <p className="text-lg font-semibold text-indigo-600 mt-2 animate-fade-up-delay">
            {badge.name}
          </p>

          {/* Counter */}
          {badges.length > 1 && (
            <p className="text-xs text-gray-400 mt-3">
              {currentIndex + 1} / {badges.length}
            </p>
          )}

          {/* Dismiss hint */}
          <p className="text-xs text-gray-400 mt-4">
            点击任意处关闭
          </p>
        </div>
      </div>

      <style jsx global>{`
        @keyframes confetti {
          0% { transform: translateY(0) rotate(0deg); opacity: 1; }
          100% { transform: translateY(100vh) rotate(720deg); opacity: 0; }
        }
        .animate-confetti {
          animation: confetti 2s ease-in forwards;
        }
        @keyframes bounceBadge {
          0%, 100% { transform: translateY(0) scale(1); }
          30% { transform: translateY(-20px) scale(1.1); }
          60% { transform: translateY(-10px) scale(1.05); }
        }
        .animate-bounce-badge {
          animation: bounceBadge 1s ease-out;
        }
        @keyframes pingSlow {
          0% { transform: scale(1); opacity: 0.3; }
          100% { transform: scale(1.5); opacity: 0; }
        }
        .animate-ping-slow {
          animation: pingSlow 1.5s ease-out infinite;
        }
        @keyframes fadeUp {
          from { opacity: 0; transform: translateY(10px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .animate-fade-up {
          animation: fadeUp 0.5s ease-out 0.3s both;
        }
        .animate-fade-up-delay {
          animation: fadeUp 0.5s ease-out 0.5s both;
        }
      `}</style>
    </div>
  );
}

export function CelebrationProvider({ children }: { children: ReactNode }) {
  const [badges, setBadges] = useState<UnlockedBadge[]>([]);
  const [showing, setShowing] = useState(false);

  const celebrate = useCallback((newBadges: UnlockedBadge[]) => {
    if (newBadges.length > 0) {
      setBadges(newBadges);
      setShowing(true);
    }
  }, []);

  const handleClose = useCallback(() => {
    setShowing(false);
    setBadges([]);
  }, []);

  return (
    <CelebrationContext.Provider value={{ celebrate }}>
      {children}
      {showing && badges.length > 0 && (
        <CelebrationOverlay badges={badges} onClose={handleClose} />
      )}
    </CelebrationContext.Provider>
  );
}

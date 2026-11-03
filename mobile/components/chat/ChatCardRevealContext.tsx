import React from 'react';
import type { FlatList, View } from 'react-native';

type RevealCard = (target: React.RefObject<View | null>) => () => void;
export const ChatCardRevealContext = React.createContext<RevealCard>(() => () => {});

interface RevealOptions {
  listRef: React.RefObject<FlatList | null>;
  viewportRef: React.RefObject<View | null>;
  offsetRef: React.MutableRefObject<number>;
  onReveal: () => void;
}

export function useChatCardReveal({ listRef, viewportRef, offsetRef, onReveal }: RevealOptions) {
  const generation = React.useRef(0);
  const timer = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  const cancel = React.useCallback(() => {
    generation.current += 1;
    if (timer.current != null) clearTimeout(timer.current);
    timer.current = null;
  }, []);
  React.useEffect(() => cancel, [cancel]);

  const reveal = React.useCallback<RevealCard>((target) => {
    cancel();
    const request = generation.current;
    // Stop automatic bottom-following before the editor adds content height.
    onReveal();
    const delays = [0, 80, 140, 260];
    const attempt = (index: number) => {
      if (request !== generation.current || index >= delays.length) return;
      timer.current = setTimeout(() => {
        if (request !== generation.current) return;
        const node = target.current;
        const viewport = viewportRef.current;
        if (!node || !viewport) { attempt(index + 1); return; }
        const active = () => request === generation.current && target.current === node
          && viewportRef.current === viewport;
        viewport.measureInWindow((_x, viewportY, _width, viewportHeight) => {
          if (!active()) return;
          node.measureInWindow((_left, targetY, _w, targetHeight) => {
            if (!active()) return;
            if (![viewportY, viewportHeight, targetY, targetHeight, offsetRef.current].every(Number.isFinite)
              || viewportHeight <= 24 || targetHeight <= 0) {
              attempt(index + 1);
              return;
            }
            // A tall editor starts below the header; a fully visible one stays put.
            const visible = targetY >= viewportY + 12
              && targetY + targetHeight <= viewportY + viewportHeight - 12;
            if (!visible) {
              listRef.current?.scrollToOffset({
                offset: Math.max(0, offsetRef.current + targetY - viewportY - 12),
                animated: false,
              });
            }
            cancel();
          });
        });
      }, delays[index]);
    };
    attempt(0);
    // An older card closing must not cancel a newer card's request.
    return () => { if (request === generation.current) cancel(); };
  }, [cancel, listRef, viewportRef, offsetRef, onReveal]);
  return { reveal, cancel };
}

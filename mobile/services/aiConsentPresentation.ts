import type { AIConsentPolicy } from './aiConsent';
import { subscribeAIConsentInvalidation } from './aiConsentState';

export type ConsentDecision = 'accept' | 'decline' | 'revoke' | 'keep';
export type ConsentPresentation = {
  policy: AIConsentPolicy;
  mode: 'request' | 'manage';
  choose: (decision: ConsentDecision) => void;
};
let current: ConsentPresentation | null = null;
const listeners = new Set<() => void>();
export const getConsentPresentation = () => current;
export function subscribeConsentPresentation(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}
function publish() { listeners.forEach(listener => listener()); }
export function showAIConsent(policy: AIConsentPolicy, mode: 'request' | 'manage'): Promise<ConsentDecision> {
  current?.choose('decline');
  return new Promise(resolve => {
    const presentation: ConsentPresentation = { policy, mode, choose: decision => {
      if (current !== presentation) return;
      current = null;
      unsubscribe();
      publish();
      resolve(decision);
    } };
    const unsubscribe = subscribeAIConsentInvalidation(() => presentation.choose('decline'));
    current = presentation;
    publish();
  });
}

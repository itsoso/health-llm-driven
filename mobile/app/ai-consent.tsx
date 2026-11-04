import React, { useEffect, useSyncExternalStore } from 'react';
import { AIConsentDialog } from '../components/AIConsentDialog';
import { getConsentPresentation, subscribeConsentPresentation } from '../services/aiConsentPresentation';

export default function AIConsentScreen() {
  const presentation = useSyncExternalStore(subscribeConsentPresentation, getConsentPresentation, getConsentPresentation);
  useEffect(() => () => { presentation?.choose('decline'); }, [presentation]);
  return <AIConsentDialog />;
}

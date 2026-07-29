type AppReloadPreparation = () => Promise<void> | void;

const preparations = new Set<AppReloadPreparation>();

export function registerAppReloadPreparation(
  preparation: AppReloadPreparation,
): () => void {
  preparations.add(preparation);
  return () => {
    preparations.delete(preparation);
  };
}

export async function prepareForAppReload(): Promise<void> {
  try {
    await Promise.all(Array.from(preparations, preparation => preparation()));
  } catch {
    throw new Error('无法安全保存当前内容，请稍后重试更新');
  }
}

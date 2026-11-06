import type { Session } from 'electron'

export async function clearDesktopCache(session: Session, origin: string): Promise<void> {
  await session.clearStorageData({ origin, storages: ['serviceworkers', 'cachestorage'] })
  await session.clearCache()
  await session.clearCodeCaches({})
}

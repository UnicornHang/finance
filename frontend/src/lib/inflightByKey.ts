import { useEffect, useState } from 'react'

/**
 * 按 key 合并进行中的异步请求。
 * 组件卸载后仍可查询/复用同一 Promise，避免重复打接口。
 */
export function createInflightRegistry<T>() {
  const map = new Map<string, Promise<T>>()
  const listeners = new Set<() => void>()

  /** 通知所有订阅方刷新禁用态 */
  function notify() {
    listeners.forEach((listener) => listener())
  }

  /** 订阅 inflight 集合变化 */
  function subscribe(listener: () => void): () => void {
    listeners.add(listener)
    return () => {
      listeners.delete(listener)
    }
  }

  /** key 是否仍有进行中请求 */
  function isPending(key: string | null | undefined): boolean {
    return Boolean(key && map.has(key))
  }

  /**
   * 若 key 已有进行中请求则直接复用；否则执行 factory 并登记。
   */
  function run(key: string, factory: () => Promise<T>): Promise<T> {
    const existing = map.get(key)
    if (existing) return existing

    const promise = factory().finally(() => {
      // 只清除本次登记，避免晚到的 finally 误删后续新一轮请求
      if (map.get(key) === promise) {
        map.delete(key)
        notify()
      }
    })
    map.set(key, promise)
    notify()
    return promise
  }

  return { subscribe, isPending, run }
}

type InflightRegistry = {
  subscribe: (listener: () => void) => () => void
  isPending: (key: string | null | undefined) => boolean
}

/** 订阅 registry，返回指定 key 是否仍在请求中 */
export function useInflightPending(
  registry: InflightRegistry,
  key: string | null | undefined,
): boolean {
  const [, setTick] = useState(0)

  useEffect(() => registry.subscribe(() => setTick((n) => n + 1)), [registry])

  return registry.isPending(key)
}

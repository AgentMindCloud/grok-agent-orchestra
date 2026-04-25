/**
 * Tiny module-level selection store. Avoids a Zustand / Jotai
 * dependency for one piece of cross-component state (the active
 * template name). Replace with a real store when 16b adds more.
 */

import { useSyncExternalStore } from "react";

type Listener = () => void;

let _selected: string | null = null;
const _listeners = new Set<Listener>();

function subscribe(cb: Listener): () => void {
  _listeners.add(cb);
  return () => {
    _listeners.delete(cb);
  };
}

function getSnapshot(): string | null {
  return _selected;
}

function getServerSnapshot(): string | null {
  return null;
}

export function useSelectedTemplate(): string | null {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

export function setSelectedTemplate(name: string | null): void {
  if (_selected === name) return;
  _selected = name;
  _listeners.forEach((cb) => cb());
}

'use client';
import { useCallback, useEffect, useState } from 'react';

export const navigationEvent = 'lifenav-navigation';
export function useNavigationParam<T extends string>(
    name: string, values: Readonly<Record<string, T>>, fallback: T,
): [T, (value: T) => void] {
    const [value, setValue] = useState<T>(fallback);
    useEffect(() => {
        const read = () => {
            const key = new URL(window.location.href).searchParams.get(name);
            setValue(key && Object.prototype.hasOwnProperty.call(values, key) ? values[key] : fallback);
        };
        read();
        window.addEventListener('popstate', read);
        window.addEventListener(navigationEvent, read);
        return () => {
            window.removeEventListener('popstate', read);
            window.removeEventListener(navigationEvent, read);
        };
    }, [name, values, fallback]);
    const select = useCallback((next: T) => {
        const key = Object.keys(values).find(key => values[key] === next);
        if (!key) throw Error('未知导航栏目');
        const url = new URL(window.location.href);
        if (url.searchParams.get(name) !== key) {
            url.searchParams.set(name, key);
            const state = { ...window.history.state };
            // Let Next copy its routing state and update useSearchParams itself.
            delete state.__NA; delete state._N; delete state.__PRIVATE_NEXTJS_INTERNALS_TREE;
            window.history.pushState(state, '', url);
        }
        window.dispatchEvent(new Event(navigationEvent));
    }, [name, values]);
    return [value, select];
}

export function sameWorkspaceRoute(left: URL, right: URL): boolean {
    const normalized = (url: URL) => {
        const query = new URLSearchParams(url.search);
        query.delete('tab'); query.delete('study'); query.sort();
        return query.toString();
    };
    return left.origin === right.origin && left.pathname === right.pathname
        && normalized(left) === normalized(right);
}

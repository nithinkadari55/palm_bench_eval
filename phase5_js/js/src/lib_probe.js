// Feature probe: which ES / host APIs the engine has natively (before shims) and after shims.
// input: {} -> JSON
globalThis.__p5.register({
  name: 'probe',
  run() {
    const env = JSON.parse(globalThis.__p5.environment());
    const t = (f) => { try { return f(); } catch (e) { return 'throws ' + (e && e.name); } };
    return JSON.stringify({
      native_before_shims: env.native,
      installed_shims: Object.keys(env.installed).sort(),
      es: {
        Intl: typeof Intl === 'object' && !Intl.__p5shim ? 'native' : (typeof Intl === 'object' ? 'shim' : 'absent'),
        WeakRef: typeof WeakRef, FinalizationRegistry: typeof FinalizationRegistry,
        IteratorHelpers: typeof Iterator === 'function' && typeof Iterator.prototype.map === 'function',
        ObjectGroupBy: typeof Object.groupBy, ArrayToSorted: typeof [].toSorted, ArrayFindLast: typeof [].findLast,
        StructuredCloneNative: env.native.structuredClone, RegExpV: t(() => new RegExp('[\\p{L}--[a-z]]', 'v').test('A')),
        SetMethods: typeof new Set().union, PromiseWithResolvers: typeof Promise.withResolvers,
        Temporal: typeof globalThis.Temporal, ShadowRealm: typeof globalThis.ShadowRealm,
        Float16Array: typeof globalThis.Float16Array, Uint8ArrayBase64: typeof Uint8Array.fromBase64,
        WebAssembly: typeof globalThis.WebAssembly, SharedArrayBuffer: typeof globalThis.SharedArrayBuffer
      },
      locale: {
        numberToLocaleString: t(() => (1234567.891).toLocaleString()),
        numberToLocaleStringDe: t(() => (1234567.891).toLocaleString('de-DE')),
        dateToLocaleDateString: t(() => new Date(Date.UTC(2026, 0, 2)).toLocaleDateString('en-US', { timeZone: 'UTC' })),
        dateToString: t(() => new Date(Date.UTC(2026, 0, 2, 3, 4, 5)).toString()),
        localeCompare: t(() => ['b', 'a', 'B', 'ä'].sort((x, y) => x.localeCompare(y)).join(',')),
        toLocaleUpperCaseTr: t(() => 'i'.toLocaleUpperCase('tr'))
      },
      globals_sample: Object.getOwnPropertyNames(globalThis).filter((k) => !k.startsWith('__')).sort()
    });
  }
});

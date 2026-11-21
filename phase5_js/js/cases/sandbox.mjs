// Hostile scripts. "limit" cases must end with a typed error inside the budget; "escape"
// cases must show that no filesystem / network / process / module access exists.
// Each script is run by the sandbox library (eval of a classic script); escape scripts
// evaluate to (or resolve to) a string starting with 'blocked' or 'absent' when the
// access is impossible, and 'LOADED' / 'ESCAPED' when it worked.
export const limits = [
  { id: 'infinite-loop', expect: ['Timeout'], script: 'for (;;) {}' },
  { id: 'infinite-loop-swallowing-catch', expect: ['Timeout'], script: 'for (;;) { try { for (;;) {} } catch (e) {} }' },
  { id: 'busy-wait-on-date', expect: ['Timeout', 'ok'], script: 'const t = Date.now(); while (Date.now() - t < 5000) {} "waited"' },
  { id: 'redos-backtracking', expect: ['Timeout'], script: '/^(a+)+$/.test("a".repeat(48) + "b")' },
  { id: 'sort-comparator-loop', expect: ['Timeout'], script: '[3, 2, 1].sort(() => { for (;;) {} })' },
  { id: 'memory-bomb-arrays', expect: ['OutOfMemory'], script: 'const a = []; for (;;) a.push(new Array(1e5).fill(1.5));' },
  { id: 'memory-bomb-map', expect: ['OutOfMemory'], script: 'const m = new Map(); for (let i = 0; ; i++) m.set(i, { i, s: "x" + i });' },
  { id: 'memory-bomb-typed-arrays', expect: ['OutOfMemory'], script: 'const l = []; for (;;) l.push(new Float64Array(1 << 20));' },
  { id: 'memory-bomb-array-join', expect: ['OutOfMemory', 'RangeError'], script: 'new Array(1e9).join("x")' },
  { id: 'deep-recursion', expect: ['StackOverflow'], script: 'function f(n) { return f(n + 1) + 1; } f(0);' },
  { id: 'deep-recursion-catch-and-retry', expect: ['StackOverflow', 'Timeout'], script: 'function f() { try { return f(); } catch (e) { return f(); } } f();' },
  { id: 'proxy-get-recursion', expect: ['StackOverflow'], script: 'const p = new Proxy({}, { get: (t, k, r) => r[k] }); p.x;' },
  { id: 'json-stringify-deep', expect: ['StackOverflow', 'OutOfMemory'], script: 'let o = {}; for (let i = 0; i < 1e6; i++) o = { a: o }; JSON.stringify(o);' },
  { id: 'huge-string-doubling', expect: ['OutOfMemory', 'RangeError', 'InternalError'], script: 'let s = "x"; for (;;) s += s;' },
  { id: 'huge-string-repeat', expect: ['RangeError', 'OutOfMemory'], script: '"x".repeat(2 ** 31)' },
  { id: 'promise-flood-chain', expect: ['JobBudget', 'Timeout'], script: '(function f() { Promise.resolve().then(f); })(); "scheduled"' },
  { id: 'promise-flood-fanout', expect: ['JobBudget', 'Timeout', 'OutOfMemory'], script: 'function f() { Promise.resolve().then(f); Promise.resolve().then(f); } f(); "scheduled"' },
  { id: 'queue-microtask-flood', expect: ['JobBudget', 'Timeout'], script: '(function f() { queueMicrotask(f); })(); "scheduled"' },
  { id: 'timer-bomb-fanout', expect: ['TimerBudget'], script: 'function t() { setTimeout(t, 0); setTimeout(t, 0); } t(); "scheduled"' },
  { id: 'timer-bomb-interval', expect: ['TimerBudget'], script: 'setInterval(() => {}, 0); "scheduled"' },
  { id: 'raf-loop', expect: ['TimerBudget'], script: '(function loop() { requestAnimationFrame(loop); })(); "scheduled"' },
  { id: 'atomics-wait-forever', expect: ['TypeError', 'Timeout'], script: 'Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0)' },
  { id: 'canvas-op-flood', expect: ['CanvasBudget', 'Timeout', 'OutOfMemory', 'absent'], script: 'if (typeof __host_canvas_backend !== "function") { "absent: no host canvas" } else { const b = __host_canvas_backend(); for (;;) b.call("lineTo", 1, 2); }' },
  { id: 'console-flood', expect: ['Timeout', 'ok'], script: 'for (let i = 0; i < 1e6; i++) console.log("spam", i); "logged"' }
];

export const escapes = [
  { id: 'require-fs', script: 'try { require("fs").readFileSync("/etc/passwd", "utf8"); "ESCAPED" } catch (e) { "blocked: " + e.name + ": " + e.message }' },
  { id: 'dynamic-import-fs', script: 'import("fs").then((m) => "LOADED " + Object.keys(m).join(","), (e) => "blocked: " + e)' },
  { id: 'dynamic-import-std', script: 'import("std").then((m) => "LOADED " + Object.keys(m).join(","), (e) => "blocked: " + e)' },
  { id: 'dynamic-import-os', script: 'import("os").then((m) => "LOADED " + Object.keys(m).join(","), (e) => "blocked: " + e)' },
  { id: 'dynamic-import-qjs-std', script: 'import("qjs:std").then((m) => "LOADED " + Object.keys(m).join(","), (e) => "blocked: " + e)' },
  { id: 'dynamic-import-qjs-os', script: 'import("qjs:os").then((m) => "LOADED " + Object.keys(m).join(","), (e) => "blocked: " + e)' },
  { id: 'dynamic-import-file-url', script: 'import("file:///etc/passwd").then(() => "LOADED", (e) => "blocked: " + e)' },
  { id: 'dynamic-import-http', script: 'import("http://127.0.0.1:9/x.js").then(() => "LOADED", (e) => "blocked: " + e)' },
  { id: 'static-import-in-script', script: 'try { (0, eval)("import fs from \'fs\'"); "LOADED" } catch (e) { "blocked: " + e.name }' },
  { id: 'fetch', script: 'typeof fetch === "function" ? fetch("http://127.0.0.1:9/").then(() => "ESCAPED: fetch present, request completed", (e) => "ESCAPED: fetch present, connection attempted (" + e + ")") : "absent: fetch"' },
  { id: 'xhr-websocket-worker', script: '["XMLHttpRequest", "WebSocket", "Worker", "importScripts", "EventSource", "navigator"].map((k) => k + "=" + typeof globalThis[k]).join(" ").includes("function") ? "ESCAPED: " + ["XMLHttpRequest", "WebSocket", "Worker", "importScripts"].filter((k) => typeof globalThis[k] === "function").join(",") : "absent: network globals"' },
  { id: 'process-env', script: 'typeof process !== "undefined" && process.env ? "ESCAPED: process.env" : "absent: process"' },
  { id: 'deno-bun-std-os', script: '["Deno", "Bun", "std", "os", "scriptArgs", "require", "module", "exports", "__dirname"].filter((k) => typeof globalThis[k] !== "undefined").join(",") || "absent: runtime globals"' },
  { id: 'std-loadfile', script: 'try { std.loadFile("/etc/passwd"); "ESCAPED" } catch (e) { "blocked: " + e.name }' },
  { id: 'os-exec', script: 'try { os.exec(["/bin/sh", "-c", "id"]); "ESCAPED" } catch (e) { "blocked: " + e.name }' },
  { id: 'webassembly', script: 'typeof WebAssembly === "object" ? "present: WebAssembly (compute only, no host imports)" : "absent: WebAssembly"' },
  { id: 'function-constructor-global', script: 'const g = (function () {}).constructor("return this")(); "blocked: Function constructor reaches only the sandbox global (" + (g === globalThis) + ")"' }
];

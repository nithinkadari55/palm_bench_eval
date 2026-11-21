// Runs one hostile classic script (cases/sandbox.mjs). The result is the script's
// completion value, awaited when it is a promise.
globalThis.__p5.register({
  name: 'sandbox',
  run(input) {
    const v = (0, eval)(input.script);
    return Promise.resolve(v).then((x) => String(x));
  }
});

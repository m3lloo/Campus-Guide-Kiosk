# Vendored front-end libraries

Third-party code served locally so the kiosk does not depend on a CDN at
runtime (and so browser tracking-prevention does not block it).

| File | Package | Version | Used by |
|---|---|---|---|
| `motion.js` | [motion](https://motion.dev) | 12.23.12 | `static/fx.js` (animations) |
| `simple-keyboard.js`, `simple-keyboard.css` | [simple-keyboard](https://github.com/hodgef/simple-keyboard) | 3.8.194 | on-screen keyboard |

## Rebuilding `motion.js`

`motion.js` is a minified ESM bundle of only the functions the app uses:

```bash
mkdir motion-build && cd motion-build
npm init -y && npm i motion@12.23.12 esbuild
echo 'export { animate, stagger, hover, press, inView, spring, scroll } from "motion";' > entry.js
npx esbuild entry.js --bundle --minify --format=esm --outfile=../static/vendor/motion.js
```

## Updating `simple-keyboard`

Copy `build/index.js` and `build/css/index.css` from the npm package
(`npm i simple-keyboard@3`) to `simple-keyboard.js` / `simple-keyboard.css`.

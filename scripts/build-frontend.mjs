import { build, context } from "esbuild";
import { readFileSync } from "node:fs";

const watch = process.argv.includes("--watch");
const entry = "frontend/src/abstractor-panel.js";
const out = "custom_components/abstractor/www/abstractor-panel.js";

const options = {
  entryPoints: [entry],
  bundle: true,
  format: "iife",
  platform: "browser",
  target: ["es2020"],
  outfile: out,
  minify: false,
  sourcemap: false,
};

if (watch) {
  const ctx = await context(options);
  await ctx.watch();
  console.log("watching");
} else {
  await build(options);
  console.log("built", out);
}

import { mkdir, cp, writeFile } from "node:fs/promises";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
await mkdir(resolve(root, "dist/css"), { recursive: true });
execFileSync(
  process.execPath,
  [resolve(root, "node_modules/typescript/bin/tsc")],
  { cwd: root, stdio: "inherit" },
);
execFileSync(
  process.execPath,
  [
    resolve(root, "node_modules/tailwindcss/lib/cli.js"),
    "-i",
    "css/styles.css",
    "-o",
    "dist/css/styles.css",
    "--minify",
  ],
  { cwd: root, stdio: "inherit" },
);
await cp(resolve(root, "index.html"), resolve(root, "dist/index.html"));
await cp(resolve(root, "assets"), resolve(root, "dist/assets"), {
  recursive: true,
});
if (process.env.PUBLIC_API_URL) {
  const url = new URL(process.env.PUBLIC_API_URL);
  if (!["https:", "http:"].includes(url.protocol) || url.username || url.password || url.search || url.hash)
    throw new Error("PUBLIC_API_URL must be an HTTP(S) base URL without credentials, query or fragment");
  await writeFile(resolve(root, "dist/js/config.js"), `export const API_BASE_URL = ${JSON.stringify(url.href.replace(/\/+$/, ""))};\n`);
}
console.log("Static frontend built in dist/");

import { execFileSync } from "node:child_process";
import { watch } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
function build() {
  try {
    execFileSync(process.execPath, [resolve(root, "scripts/build.mjs")], {
      cwd: root,
      stdio: "inherit",
    });
  } catch {
    console.error(
      "Build failed. Fix the errors; the last successful preview remains available.",
    );
  }
}
build();
await import("../server.mjs");
let timer;
for (const path of ["src", "css", "assets", "index.html"])
  watch(resolve(root, path), { recursive: true }, () => {
    clearTimeout(timer);
    timer = setTimeout(build, 200);
  });

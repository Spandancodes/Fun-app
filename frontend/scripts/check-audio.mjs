import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { resolve } from "node:path";

// Lock the exact approved recordings, not just filenames or non-empty placeholders.
const expected = {
  "login_right.mp3": "c28048fa107fa3e5c5d398c9517e63822fe23543aeb244078f5f9cdfdd7459ea",
  "login_wrong.mp3": "21346129af26d15210a93232066be54ccb509c6b5d93f92dc384f58271b55870",
  "no_first.mp3": "964a15f32e89c9465605f68aea44423d37b6503b1f10e58c47e69efaf4845c1e",
  "no_third_alarm.mp3": "253f1544c2af99d9068d01a619c0ddf372ce02e7b1879ca9643a1acc01e5c6e6",
  "yes_date_song.mp3": "ff6b1dbf15edf57bb4475fe0e796baca04c59432b92a28f8b588af4f01df0ac0",
};
const exporting = process.argv[2] === "--export";
if (exporting && process.env.STATIC_EXPORT !== "true") process.exit(0);
const root = exporting ? "out" : (process.argv[2] || "public");
for (const [file, digest] of Object.entries(expected)) {
  const path = resolve(root, "audio", file);
  let data;
  try { data = readFileSync(path); }
  catch { throw new Error(`Required audio missing: ${path}. Refusing to build a silent deployment.`); }
  if (createHash("sha256").update(data).digest("hex") !== digest)
    throw new Error(`Audio differs from the approved recording: ${path}`);
}
console.log(`Verified ${Object.keys(expected).length} exact audio assets in ${root}/audio`);

import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"

const stream = await readFile(new URL("../lib/stream.ts", import.meta.url), "utf8")
const compose = await readFile(new URL("../../docker-compose.yml", import.meta.url), "utf8")
const nextConfig = await readFile(new URL("../next.config.ts", import.meta.url), "utf8")

assert.match(stream, /NEXT_PUBLIC_BACKEND_URL \|\| ""/)
assert.doesNotMatch(stream, /NEXT_PUBLIC_BACKEND_URL \|\| "http:\/\/localhost:8001"/)
assert.match(stream, /Unable to reach the agent service/)
assert.doesNotMatch(compose, /NEXT_PUBLIC_BACKEND_URL/)
assert.match(nextConfig, /source\s*:\s*"\/chat"/)
assert.match(nextConfig, /source\s*:\s*"\/workflows\/:path\*"/)

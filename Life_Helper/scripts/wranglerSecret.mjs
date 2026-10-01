/**
 * Shared by the edge setup scripts: run a pinned Wrangler against
 * edge/wrangler.toml, and store a secret by piping it to
 * `wrangler secret put` on stdin — so the value never appears in a command
 * line, a shell history, a log, or a file.
 */
import { spawn } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

export const WRANGLER = 'wrangler@4.130.0'
export const PROJECT_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
// Relative, not absolute: this repo's absolute path has spaces in it, and
// on Windows the command below runs through a shell.
const CONFIG = 'edge/wrangler.toml'

/** A `[vars]` value from edge/wrangler.toml, or '' if unset. */
export function wranglerVar(name) {
  const toml = readFileSync(join(PROJECT_ROOT, CONFIG), 'utf8')
  const match = new RegExp(`^\\s*${name}\\s*=\\s*"([^"]*)"`, 'm').exec(toml)
  return match ? match[1] : ''
}

export function putSecret(name, value) {
  return new Promise((resolve, reject) => {
    const child = spawn('npx', ['--yes', WRANGLER, 'secret', 'put', name, '--config', CONFIG], {
      cwd: PROJECT_ROOT,
      stdio: ['pipe', 'inherit', 'inherit'],
      // npx is a .cmd shim on Windows, which Node only runs through a shell.
      shell: process.platform === 'win32',
    })
    child.on('error', reject)
    child.on('exit', (code) => {
      if (code === 0) resolve()
      else reject(new Error(`wrangler secret put ${name} exited with code ${String(code)}`))
    })
    child.stdin.end(value)
  })
}

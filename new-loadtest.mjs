#!/usr/bin/env node
// Start Claude Code in this repo and run /new-loadtest. Works on Windows, macOS and Linux.
//
//   node rata-loadtest/new-loadtest.mjs                           interview: Claude asks what to test
//   node rata-loadtest/new-loadtest.mjs tests/<name>/CONTEXT.md   use a form you already filled in
//   WORKSPACE=/path/to/workspace node rata-loadtest/new-loadtest.mjs
//
// From a workspace package.json:  "loadtest:new": "node rata-loadtest/new-loadtest.mjs"
//   npm run loadtest:new
//   npm run loadtest:new -- tests/<name>/CONTEXT.md
//
// Claude gets read access to the frontend and backend repos next to this one, so it can find the
// requests in the code. It reads branches with git fetch/show only and never switches your checkout.
import { spawn, spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const repoDir = dirname(fileURLToPath(import.meta.url))
const workspace = process.env.WORKSPACE || dirname(repoDir)
const context = process.argv[2]
const isWindows = process.platform === 'win32'

// Find claude on PATH. On Windows it can be claude.exe (native install) or claude.cmd (npm install).
function findClaude() {
  const lookup = isWindows
    ? spawnSync('where', ['claude'], { encoding: 'utf8' })
    : spawnSync('sh', ['-c', 'command -v claude'], { encoding: 'utf8' })
  if (lookup.status !== 0) return null
  const found = lookup.stdout.split(/\r?\n/).map((line) => line.trim()).filter(Boolean)
  if (!isWindows) return found[0] ?? null
  return found.find((p) => /\.exe$/i.test(p)) ?? found.find((p) => /\.cmd$/i.test(p)) ?? null
}

const claude = findClaude()
if (!claude) {
  console.error("Claude Code ('claude') is not installed or not on PATH. See https://docs.claude.com/en/docs/claude-code")
  process.exit(1)
}

const args = []
for (const repo of ['stackboard', 'rata-dynamic']) {
  const path = join(workspace, repo)
  if (existsSync(join(path, '.git'))) {
    args.push('--add-dir', path)
  } else {
    console.warn(`Warning: ${repo} not found at ${path}. Claude will ask for its path, or set WORKSPACE.`)
  }
}
args.push(context ? `/new-loadtest ${context}` : '/new-loadtest')

// Windows can only start a .cmd file through the shell: build the command line with quoted arguments.
const child = /\.cmd$/i.test(claude)
  ? spawn([`"${claude}"`, ...args.map((a) => `"${a}"`)].join(' '), { cwd: repoDir, stdio: 'inherit', shell: true })
  : spawn(claude, args, { cwd: repoDir, stdio: 'inherit' })

child.on('error', (error) => {
  console.error(error.message)
  process.exit(1)
})
child.on('exit', (code) => process.exit(code ?? 0))

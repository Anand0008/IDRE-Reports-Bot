# Running IDRE Local in Production Build Mode

For derived-dom validation at 67K-case scale, dev mode (`npx next dev`) is too slow. Use production build.

## One-time build (after IDRE source changes)

```bash
cd /c/Users/anand/Downloads/local/idre
npx next build
```

Builds `.next/` output. Takes 2-5 min. Reusable until source files change.

## Start in production mode

`NODE_ENV` MUST be set to `development` for `/api/dev/auto-login` to work — that route gates on `NODE_ENV !== "development"` returning 404. Even in prod build, we want the dev-login route to function.

PowerShell:
```powershell
$env:NODE_ENV = "development"; npx next start --hostname 127.0.0.1 --port 3000
```

Git Bash:
```bash
NODE_ENV=development npx next start --hostname 127.0.0.1 --port 3000
```

Wait for `Ready in <Xs>`. Pages should now render in 1-3s instead of 30+.

## Verify it's working

```bash
# Auto-login should set the session cookie
curl -sS -I --max-time 15 "http://127.0.0.1:3000/api/dev/auto-login" | grep -iE "HTTP|set-cookie"
# Expect: HTTP/1.1 307 + set-cookie: better-auth.session_token=...

# Cases page render should be fast
curl -sS -c /tmp/cj.txt "http://127.0.0.1:3000/api/dev/auto-login" -L --max-time 30 -o /dev/null
time curl -sS -b /tmp/cj.txt "http://127.0.0.1:3000/dashboard/cases?status=PENDING_RFI&limit=1" -o /dev/null --max-time 60
# Expect: real time <5s
```

## When to rebuild

After editing IDRE source files (TypeScript/TSX). `.env` changes do NOT need a rebuild (read at startup).

## Trade-offs vs dev mode

- No hot-reload of source changes
- React errors logged to server console (not displayed in-page)
- 5-10x faster server-render
- **Required for the derived-dom suite at production scale**

## Reverting to dev mode

```bash
cd /c/Users/anand/Downloads/local/idre
npx next dev
```

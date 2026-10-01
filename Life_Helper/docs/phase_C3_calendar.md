# Phase C, Part C3 — Google Calendar (read-only) and capacity

Status: **done (2026-10-02).** Built and tested against the real Worker
code in a real browser with only Google faked, then connected live: the
Worker is deployed, Google is connected, and the three live checks —
token survives a redeploy, a revoke prompts a reconnect, Today works
offline from cache — all passed (see "Live checks" below). No card was
needed anywhere (`docs/cost_ledger.md`).

## What's in place

**Edge (`edge/`, surface EDGE)** — the Worker Part D1 will grow into:

- `edge/src/index.ts` — `GET /calendar/events?from&to`, and nothing else.
  CORS is limited to `ALLOWED_ORIGINS` (the Pages app and local dev).
  Authentication uses one device key (the `DEVICE_TOKEN` secret) sent as a
  bearer token, compared by SHA-256 digest so timing reveals nothing. It
  fails closed: no key configured, or one too short to be generated, means
  every request is refused.
- `edge/src/google.ts` — refresh token → access token → the primary
  calendar's events (`singleEvents=true`, so recurring events arrive
  expanded, by Google, correctly) → normalized. `fields=` limits Google's
  response to id, title, status, free/busy, and times. Attendees,
  descriptions, and locations never leave Google.
- `edge/src/contract.ts` — the response and error shapes the app and
  Worker share. It's imported by the app with `import type` only, so no
  Worker code reaches the client bundle.
- `edge/wrangler.toml` — free plan, no bindings. Secrets are never in it.

**Local setup (`scripts/`, surface LOCAL):**

- `pnpm calendar:connect` — runs Google's consent once, on your computer:
  a loopback redirect, PKCE, a state check, `calendar.readonly` only. It
  confirms the calendar permission was actually granted and the Calendar
  API answers, then pipes the refresh token (and client secret) straight
  into `wrangler secret put`. They're never printed, never written to disk,
  and the app never sees them.
- `pnpm edge:device-key` — generates the device key, stores it on the
  Worker, and prints it once so you can enter it on each device.
- `pnpm edge:deploy` — deploys the Worker with a pinned Wrangler
  (`4.130.0`).

**App:**

- `src/calendar/calendarStore.ts` — two per-device values in
  localStorage: the connection (Worker address and device key) and the
  event cache.
- `src/calendar/calendarSync.ts` + `useCalendar.ts` — refreshes happen
  **on app focus and at most every 15 minutes, never on a timer**: on
  mount, `focus`, `visibilitychange`→visible, and `online`, each throttled
  against the cache's last attempt. There's no interval anywhere; a test
  spies on `setInterval`/`setTimeout` across two simulated hours to prove
  it. A failed refresh keeps the cached events and records why.
- `src/calendar/capacity.ts` — free time as waking hours, minus busy
  events, minus a buffer; plus the top 3's estimated commitment.
- `src/today/CalendarPanel.tsx` — Today's events from the cache, with a
  freshness line that always says how old they are, and a plain prompt for
  each problem that needs you (reconnect, a wrong key, an unfinished setup).
- `src/today/CapacityNote.tsx` — under the three: "About 3h 10m free for
  the rest of today · your three need about 2h". If they need more, it adds
  a plain note that it may not all fit. No red, no "over capacity."
- `src/routes/SettingsRoute.tsx` (`/settings`, now in the nav) — the
  calendar connection, waking hours and buffer, and the evening reminder
  time.
- `DAY_TASKS_SQL` now selects `estimate_min` (from capture's `~45m`).

## Setup runbook

Do these in order. **If Google asks for a card at any point, stop** and
tell me — Decision 12's fallback (C3 without calendar data) applies, and
the ledger records it.

**1. Google Cloud (no free trial):**

1. Open `https://console.cloud.google.com/projectcreate`, accept the
   terms, and create a project (for example `life-helper`). Don't click
   "Start free trial" or "Activate" — that's the flow that wants a card.
2. APIs & Services → Library → **Google Calendar API** → Enable.
3. Google Auth Platform (OAuth consent screen) → Get started. Audience
   **External**. App name "Life Helper", your email for support and
   contact.
4. Data access → Add or remove scopes → tick only
   `.../auth/calendar.readonly` (Google Calendar API) → Update → Save.
   Google asks "How will the scopes be used?": say it reads event titles,
   times and busy/free for today and tomorrow to show the day and estimate
   free time, never writes, and that data isn't stored server-side,
   shared, or sold. Leave the demo video blank; it's only for verification.
5. Branding → homepage `https://life-helper.pages.dev`, privacy policy
   `https://life-helper.pages.dev/privacy`, authorised domain
   `life-helper.pages.dev`. Publishing is greyed out until these are set;
   the policy page is `public/privacy.html`, served by Pages.
6. Audience → **Publish app** ("In production"). This matters. In
   "Testing", Google expires refresh tokens after 7 days, which would fail
   C6's "calendar sync survives a full week" exactly on day 7. Unverified
   and in production, you'll see a "Google hasn't verified this app"
   screen once during consent. Choose Advanced → Go to Life Helper; it's
   your own app. Don't submit for verification; it isn't needed for your
   own account.
7. Clients → Create client → **Desktop app** → Create. Keep the Client ID
   and Client secret to hand.

**2. The Worker (from `Life_Helper/` on your computer):**

1. Put the Client ID in `edge/wrangler.toml` under `[vars]` as
   `GOOGLE_CLIENT_ID = "…apps.googleusercontent.com"`. It's public by
   design, so it's fine to commit.
2. `npx wrangler@4.130.0 login` — a browser sign-in to Cloudflare.
3. `pnpm edge:deploy` — note the address it prints,
   `https://life-helper-edge.<your-subdomain>.workers.dev`. On a first
   deploy Wrangler may ask you to pick a free `workers.dev` subdomain.
4. `pnpm edge:device-key` — copy the key it prints.
5. `pnpm calendar:connect` — paste the client secret at the hidden prompt,
   then approve in the browser.

**3. Each device:** Settings → Calendar → the Worker address and the
device key → Connect. It should say "Working. Last updated just now."

**4. Close the remaining DoD items**, and record them here and in
`docs/cost_ledger.md` (done 2026-10-02 — see "Live checks"):

- _Refresh token survives a redeploy:_ `pnpm edge:deploy` again, then
  Settings → Check now → still "Working."
- _Revoked token → reconnect prompt:_ remove Life Helper at
  `https://myaccount.google.com/permissions`, then Check now. Today should
  show "Google Calendar needs reconnecting…". Running
  `pnpm calendar:connect` again fixes it.
- _Offline from cache:_ airplane mode on the phone, open the app. The
  events are still there, with "Offline — calendar as of …".

## Live checks (2026-10-02)

Run against the real Google account and the deployed Worker, all passed:

| Check                             | How                                                                     | Result                                                                              |
| --------------------------------- | ----------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| Refresh token survives a redeploy | `pnpm edge:deploy` again, then Settings → Check now                     | ✅ still "Working"                                                                  |
| Revoked token → clear reconnect   | Removed Life Helper at myaccount.google.com/permissions, then Check now | ✅ Today showed the reconnect prompt, no crash; `pnpm calendar:connect` restored it |
| Today renders offline from cache  | Airplane mode on the phone, opened the app                              | ✅ events shown from cache, with "Offline — calendar as of …"                       |

## Decisions, and why

**Consent runs locally, not in the app.** The plan says the Worker holds
the refresh token as a Wrangler secret (Parts C3 and D1). A Worker can't
write its own secrets, since only the Wrangler CLI can, so the one-time
consent happens on your computer and pipes straight into
`wrangler secret put`. The trade-off: reconnecting after a revoke means
running `pnpm calendar:connect` on your computer, not tapping a button on
the phone. The app's prompt says exactly that. The alternative (OAuth
endpoints on the Worker, token in KV) would move the token out of Wrangler
secrets and add a storage component to Decision 11's table. Worth
revisiting only if reconnecting turns out to be frequent.

**A device key, until Part D3.** The Worker must refuse strangers:
without a key, anyone who found the `workers.dev` address could read the
calendar. D3's pairing replaces the shared key with per-device tokens. The
key is the app's credential for its own Worker, not a Google token, and
Settings only accepts an `https://` address for it (or `localhost` for
`wrangler dev`).

**The event cache is per-device localStorage, not the database.** It's
Google's data, not yours. Every device fetches its own copy, and routing
it through `mutate()` would write ops on every refresh and replicate them
to every device in Phase D for nothing. Losing it only costs a refetch.

**Today and tomorrow are fetched.** Tomorrow is for the evening shutdown's
planning, and costs nothing extra (it's one request either way).

**Capacity is what's left, not the whole day.** At 6pm, "you had 9 hours
today" doesn't help decide what fits. So free time runs from now (or from
waking) to the end of waking hours. The buffer (default 60 minutes, for
meals, travel, and switching) shrinks in proportion as the day goes on.
All-day events and events marked "free" don't count; overlapping events
count once. Waking hours default to 07:00–23:00, can run past midnight,
and are built from local date fields, so a DST day is handled correctly.

**Capacity only appears when the cache actually covers today.** Computing
it from no events would claim the whole day is free.

**Tasks without an estimate aren't guessed.** The note says "(1 without an
estimate)" rather than inventing a duration. If none of the three have
one, it shows only the free time.

**Everything needing you says what to do, in plain words.** A problem
note carries an accent stroke and the words; there's never red. Offline
and "Google failed just now" don't raise a prompt at all. They only change
the freshness line, because there's nothing for you to do about them.

## Things found along the way

- **The e2e first passed for the wrong reason.** It routed the app's
  Worker calls through Playwright's `page.route()` into the real
  `handle()`. A mutation check — deliberately setting a wrong
  `ALLOWED_ORIGINS` — still passed: Chromium doesn't apply CORS to
  responses Playwright fulfils. The spec now serves `handle()` over real
  HTTP on its own `127.0.0.1` port, so the app's calls are genuinely
  cross-origin. The same mutation now fails all four tests.
- **Google's 7-day expiry for "Testing" apps** (above) would have broken
  C6 on day 7. It's now step 6 of the runbook, not a surprise.
- **Publishing needs a privacy policy.** Google greys out "Publish app"
  until Branding has a homepage and privacy policy URL. The policy is a
  standalone `public/privacy.html` on the existing Pages site, excluded
  from the service worker's navigation fallback. Pages 308-redirects
  `/privacy.html` to `/privacy`, so the fallback excludes both.
- **Invisible characters in a script.** The file-writing tool turned the
  `\u0003` and `\u007f` escapes in the connect script's hidden-input
  prompt into literal control bytes. They behaved the same, but were
  invisible in any editor. They're escapes again, and a scan of `src/`,
  `edge/`, and `scripts/` for control characters is clean.
- **A grammar bug, found by looking.** "Offline — showing the calendar
  from at 7:31 PM" read wrong. The freshness line now uses its own "as of"
  wording ("Offline — calendar as of 7:31 PM").
- **Event rows wrapped on a phone.** Every event took two lines at 375px.
  Tightening the time column fits a normal event on one line (74px rows
  down to 49px).

## Verification

```bash
pnpm verify      # typecheck + lint + format + unit tests + build — green
pnpm test:e2e    # Playwright, including e2e/calendar.spec.ts — green
```

| DoD requirement                                                           | Where                                                                                                                                                                                                                                                        |
| ------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| OAuth completes and the refresh token survives a Worker redeploy          | ✅ Live, 2026-10-02: `pnpm calendar:connect` completed, then a second `pnpm edge:deploy` and Check now still said "Working"                                                                                                                                  |
| events render on Today                                                    | `TodayRoute.test.tsx`; `e2e/calendar.spec.ts` (real Worker code, real HTTP, fake Google)                                                                                                                                                                     |
| capacity is computed and displayed                                        | `capacity.test.ts` (clipping, overlaps, all-day and free events, pro-rated buffer, past-midnight bedtimes, a DST day); `TodayRoute.test.tsx`; `e2e/calendar.spec.ts` ("your three need about 1h 30m")                                                        |
| the token is never present in client-side storage or in the repository    | Structural: the app has no code path that receives it; the connect script pipes it to `wrangler secret put`; `.dev.vars` and `.wrangler` are gitignored. Tested: `edge/src/index.test.ts` checks that no Worker response, in any branch, contains any secret |
| Today renders fully offline from cache with a visible staleness indicator | `e2e/calendar.spec.ts`: second navigation (service worker in control), network cut, **full page reload**. Events render from cache, and a refresh shows "Offline — calendar as of …". ✅ Live on the phone in airplane mode, 2026-10-02                      |
| a revoked token produces a clear reconnect prompt rather than a crash     | `edge/src/index.test.ts` (`invalid_grant`, a narrowed scope, Calendar API 401/403); `e2e/calendar.spec.ts` (a revoke mid-session: the prompt appears, last events and tasks stay). ✅ Live, 2026-10-02: revoked at myaccount.google.com, the prompt appeared |

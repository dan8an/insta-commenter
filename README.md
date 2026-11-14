# InstaComment — local browser edition

Run InstaComment on your Mac and publish individual Instagram comments through a dedicated, visible browser. No Facebook account, Meta developer app, OAuth credentials, professional account conversion, paid API, or HTTPS tunnel is required by this application. You still need an Instagram account able to access and comment on the target post.

The React frontend and FastAPI/SQLite backend are retained. The backend controls a local Node/Playwright worker. Login happens directly in Instagram; the app never asks for your Instagram password or 2FA code. This is unofficial browser automation, not an official Instagram API integration. Instagram can interrupt it with login challenges or UI changes. There is no evasion or automatic retry.

## Start (existing installation)

Stop your old backend/frontend terminals with **Ctrl+C**, then run:

```sh
cd /Users/danieleitan/Desktop/Projects/insta-commenter
./scripts/start-local.sh
```

Open **http://localhost:5173**. Keep that exact origin; don't use an ngrok address or mix `127.0.0.1` into the frontend URL.

The launcher sets browser mode, loopback binding, and local cookie settings, overriding old MODE/demo/OAuth/tunnel values. It uses Google Chrome already installed on your Mac. It checks for occupied ports before starting and shuts down both servers with Ctrl+C. It does not modify your `.env` or stop your existing processes for you.

If dependencies have changed since your last installation:

```sh
cd frontend
npm install
cd ..
```

## First installation

Requires Python 3.11+, Node 20+, and Google Chrome.

```sh
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
cd frontend
npm install
cd ..
./scripts/start-local.sh
```

Python Playwright is **not** required. The browser worker uses Node Playwright from the frontend installation.

If you prefer a dedicated downloaded Chromium instead of the Chrome executable:

```sh
cd frontend
npm run browser:install
cd ..
BROWSER_CHANNEL=chromium ./scripts/start-local.sh
```

Either option uses a separate InstaComment profile, never your everyday Chrome profile.

## Connect and publish

1. Click **Open Instagram browser**. A separate Chrome window opens Instagram.
2. Sign in yourself. Complete any 2FA/security checks and dismiss cookie/login dialogs manually. Use Instagram's English interface for the current selectors.
3. Return to InstaComment and click **Check connection**. Verify the displayed username.
4. Paste a `/p/` or `/reel/` HTTPS permalink, write your comment, and click **Publish Comment** once.
5. Leave the dedicated browser on the selected post until the operation finishes. Don't switch accounts, navigate away or manually post the same text during the operation.
6. Independently inspect your first comment on Instagram to verify the integration against your account.

The post can belong to another account if Instagram's ordinary browser UI permits you to comment. Private/unavailable posts and disabled comment controls may prevent posting. Browser mode supports top-level comments only; reply directly in Instagram if needed.

## What counts as success

Before submitting, the worker checks the visible signed-in profile, URL, comment field and Post button. It refuses if an identical comment by that username is already visible. It fills the text, clicks Post **once**, reloads the post, and looks for the exact normalized text under that username in an individual rendered comment row with a timestamp and Reply control.

- **Published:** comment text/author were found after reload. This is browser verification, not an API receipt. An ID is included only if the visible page supplies a comment permalink; otherwise it stays null.
- **Unsupported/failed:** the worker could not prepare the comment or Instagram requires attention. Inspect the browser for the next step.
- **Unknown:** a click may have reached Instagram but confirmation was unavailable. There is no automatic resubmission. Check the actual post, then click **I checked Instagram** in Recent activity to unlock further publishing. Acknowledgement records `reviewed`, not success.

Unknown or pending attempts block further publishing until resolved; after a backend restart, interrupted attempts become unknown. One browser command runs at a time. A persistent request key and a short duplicate-content window also guard accidental resubmission. This is not an exactly-once delivery guarantee: comment sorting, delayed rendering or hidden comments can prevent verification. Missing a visible comment does not establish that it wasn't posted.

Text is limited to 2,200 Unicode code points by the application. Emojis and line breaks are supported. Tracking query parameters are removed; non-Instagram URLs and unsupported paths are rejected.

## Local data and disconnection

- Database: `backend/instacomment.db` when launched with the script.
- Browser sign-in: `backend/.local/browser-profile/` (directory restricted to your local OS user).
- Automatically generated session signing secret: `backend/.local/session-secret`.

The `.local` directory is ignored by Git. Browser profile data includes sensitive authentication state; don't share or commit it. No Instagram cookies are exported to the frontend or reused in private HTTP API calls. Browser sessions persist across restarts in that dedicated profile.

**Settings → Disconnect & clear browser sign-in** closes the dedicated browser and deletes its local profile. Activity history is retained. Closing the app alone preserves sign-in for next time.

This is deliberately one local user: browser-mode activity is shared across your local InstaComment tabs and survives app restarts. Backend checks require loopback clients, local Host headers, an exact Origin and a session-bound CSRF token. Do not expose this service with a tunnel, bind it to a LAN/public interface, deploy it to a cloud host or start multiple backend workers. Any process running as your local OS user remains within the local trust boundary.

## Demo mode

To use the simulated studio, start the servers manually in separate terminals:

```sh
cd backend
MODE=demo FRONTEND_ORIGIN=http://localhost:5173 COOKIE_SECURE=false .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

```sh
cd frontend
npm run dev -- --port 5173 --strictPort
```

Demo scenario buttons cover simulated success, inaccessible targets, permissions, expired credentials, rate limits, provider errors and unknown outcomes. Nothing is posted to Instagram. Old API feasibility notes and API-client unit tests are retained for reference; the browser app no longer uses Meta OAuth or Graph publishing endpoints. The old Vercel/Render configurations are not deployment targets for this local edition; Docker Compose remains demo-only.

## Tests and current verification

```sh
cd backend
.venv/bin/python -m pytest tests -q
cd ../frontend
npm test
npm run build
npm run test:browser-dom
npm run test:browser
npm run test:e2e
```

- Backend: 45 tests passed, including browser dispatch, idempotency, persistence, local-host/CSRF checks, unknown-outcome acknowledgement and serialized browser access.
- Frontend: 10 Vitest tests passed, including browser connection controls, publishing and manual acknowledgement.
- Production frontend build passed.
- Five DOM verification tests passed: author/text association, rejection of captions, whitespace/Unicode and ID handling.
- Two Playwright UI tests passed when run from the user’s normal Terminal. Desktop dark-mode and mobile screenshots were inspected; no console errors were captured. The saved traces confirmed HTTP 200 from Vite at localhost:5173. These tests mock browser-mode API calls and do not verify real Instagram publishing.
- Browser integration fixtures intercept **all** browser requests and simulate Instagram pages; they never submit real comments. Chrome launch is blocked inside the implementation sandbox. Run the worker fixture suite from your own Terminal; live Instagram verification remains separate.
- No real Instagram comment was posted during this rebuild. Live compatibility with your account must be verified with the first manual test above.

If you see “Could not open the browser,” check Chrome is installed and no other InstaComment backend owns its profile. If you see “Could not identify your profile,” finish login, use English, dismiss dialogs and check again. If Instagram's UI no longer matches the selectors, the app stops; share the visible error rather than credentials or browser-profile files.

## Screenshot and console-error QA

With Vite already running at http://localhost:5173, run this from your normal Terminal:

```sh
cd frontend
npm run test:ui
```

This runs desktop and mobile browser-mode UI workflows against the existing frontend, mocking the backend routes so it cannot open Instagram or post real comments. It tests connection controls, publishing, dark appearance, uncertain-result acknowledgement, and horizontal overflow. Each completed test saves a full-page screenshot and a JSON console-error attachment under `frontend/test-results/`; the HTML report is in `frontend/playwright-report/index.html`. Unexpected JavaScript exceptions or console errors fail the test. Traces are retained on failure.

`npm run test:e2e` separately starts isolated demo servers on ports 5175/8005 and runs both real-demo and mocked-browser workflows. It will not reuse your running app servers.

During this rebuild, a Vite listener was found on port 5173, but the sandbox denied HTTP connections (`Operation not permitted`) and denied starting another Vite listener (`listen EPERM`). Both Playwright UI tests failed during Chrome launch (`SIGABRT`/`EPERM`), before loading a page. The user subsequently ran these tests outside the sandbox. The first run exposed an overly strict username locator; that assertion and a Tailwind outline-class styling collision were fixed. The next run passed both tests, generated inspected desktop/mobile screenshots, and reported no console errors. This verifies the simulated UI workflow, not real Instagram publishing.

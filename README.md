# InstaComment — local publishing studio

Compose Instagram comments in a focused workspace, preview your draft, and publish through a dedicated, visible Chrome window on your Mac. Sign in directly on Instagram; the app never asks for your password or 2FA code.

## Download and launch on macOS

**[Download InstaComment for macOS](https://github.com/dan8an/insta-commenter/releases/latest/download/InstaComment-macOS.zip)** · [Release notes and all downloads](https://github.com/dan8an/insta-commenter/releases)

### One-time setup

Install these prerequisites if they are not already on your Mac:

- **Python 3.11 or newer:** [Python for macOS](https://www.python.org/downloads/macos/). Use the installer and its included certificate-installation instructions.
- **Node.js 22 or newer, with npm:** [Node.js downloads](https://nodejs.org/en/download).
- **Google Chrome:** [Download Chrome](https://www.google.com/chrome/) and place it in `/Applications`.

The launcher checks these requirements and tells you what is missing. It installs the app's Python and JavaScript dependencies automatically, without administrator access. An internet connection is needed for initial setup and new versions.

### Start the app

1. Download **InstaComment-macOS.zip** from the link above. Choose that release asset, not GitHub's automatically generated “Source code” archive.
2. Unzip it and move the entire **InstaComment** folder somewhere permanent, such as your home folder. Keep `InstaComment.command` and the other files together.
3. Double-click **InstaComment.command**. A Terminal window opens and shows installation or update progress. The first launch may take several minutes.
4. When both servers are ready, the launcher opens **http://localhost:5173** in your default browser.
5. Keep the Terminal window open while using the app. To stop, select that window and press **Ctrl+C**. Closing the app's browser tab alone does not stop it.

To start again, double-click the same launcher. You can make a Finder alias to `InstaComment.command` for easier access, keeping the original folder intact.

This is an unsigned script launcher, not a signed/notarized macOS application. If macOS blocks your downloaded copy, follow [Apple's instructions for opening trusted downloaded software](https://support.apple.com/en-us/102445). Do not disable Gatekeeper globally.

### Automatic updates

On each launch, the launcher checks this repository's **latest stable GitHub release**. It downloads newer versions, verifies the ZIP against the release's SHA-256 checksum, installs their dependencies, and starts the new app. Ordinary UI and technical changes appear once a maintainer publishes a new release and you restart; un-released commits on `main` do not reach launcher users.

- Releases install into separate version folders. Existing data is kept outside those folders.
- The active-version pointer changes only after both servers respond successfully.
- If GitHub is unavailable, an installed or bundled release can still start. A first-time dependency installation still needs internet access.
- If installing a new release's dependencies fails, the launcher attempts to use the previously working installation.
- Startup failures leave the previous version recorded; there is no automatic database rollback. The launcher shows the error instead of hiding it.
- Ordinary app updates require no changes to the downloaded launcher. A future change to the launcher protocol or system prerequisites may require downloading a fresh launcher.

To skip the update check, run this from the extracted folder in Terminal:

```sh
./InstaComment.command --offline
```

Use `--no-open` to start the servers without opening the workspace tab automatically. Only one launcher can run at a time. It will not stop an existing app or another program using ports 5173 or 8000.

## Connect and publish

1. In **Browser session**, click **Open Instagram browser**. A separate Chrome window opens Instagram.
2. Sign in yourself and complete any 2FA/security checks. Dismiss cookie dialogs and use Instagram's English interface.
3. Return to InstaComment and click **Check connection**. Verify the displayed username.
4. Paste an Instagram `/p/` or `/reel/` HTTPS link, write your comment, and check the live draft preview. The preview is illustrative; Instagram's layout can differ.
5. Leave **Times to post** at **1** for one submission. A larger value requests that many sequential submissions and stops at the first unconfirmed result.
6. Click **Publish Comment**. Leave the dedicated Instagram window on the selected post until the operation finishes. Do not navigate away, switch accounts, or manually submit the same comment during an operation.
7. Inspect **Recent activity** and independently check your first published comment on Instagram.

You can comment on posts that your account can access and whose comment controls are available. Browser mode supports top-level comments; reply to existing comments directly on Instagram. Comments are limited to 2,200 Unicode characters, including emojis and line breaks.

No Facebook account, Meta developer app, professional-account conversion, paid API, or tunnel is required. This is unofficial browser automation, not an official Instagram API integration. Instagram can interrupt it with security challenges, limits, or UI changes; the app does not bypass them or automatically retry an uncertain submission.

## Understanding results

The worker checks the signed-in profile and comment controls, submits the comment, reloads the post, and looks for the text under your username in a rendered comment row.

- **Published:** the text and author were found after reload. This is browser verification, not an API receipt. A comment ID appears only if Instagram exposes one in the page.
- **Unsupported / failed:** inspect the reason and the Instagram window before trying again.
- **Unknown:** a submission may have reached Instagram, but verification failed. Check the actual post, then click **I checked Instagram** in Recent activity to unlock publishing. This records **reviewed**, not success.

Pending or unknown attempts block further publishing. After a backend restart, interrupted attempts become unknown. Each click on Publish is a new attempt; repeated text can create duplicate comments. Comment sorting, delays, and hidden comments can prevent verification, so a missing visible comment does not prove it was never posted.

## Your local data

Downloaded-launcher installations use:

```text
~/Library/Application Support/InstaComment/
  current.json                 Last successfully started release
  versions/                    Installed app versions and dependencies
  data/instacomment.db          Activity history
  data/.local/browser-profile/  Dedicated Instagram sign-in
  data/.local/session-secret    Local session signing secret
```

The dedicated profile is separate from your normal Chrome profile. It contains sensitive authentication state; do not share or commit it. Updates preserve this directory. Keep a backup of `data/` if the activity history matters to you, with the app fully stopped before copying it.

**Settings → Disconnect & clear browser sign-in** closes the Instagram browser and removes that profile. Activity history is retained. Stopping the launcher preserves both sign-in and history for next time.

**Existing source-checkout users:** the downloaded launcher uses its own data directory. Your existing `backend/instacomment.db` and `backend/.local/` are left untouched; sign in once in the new installation. To keep using your existing data without migration, use the source-checkout instructions below.

To uninstall, stop the app and remove the downloaded folder. Removing `~/Library/Application Support/InstaComment/` also permanently removes installed versions, sign-in, and activity history; keep it if you want those preserved.

The app is for one local user. Keep the workspace at **http://localhost:5173**. Do not expose the backend through tunnels, bind it to a public/LAN interface, or run multiple backend workers. Backend checks require local clients, local Host headers, the exact frontend Origin, and a session-bound CSRF token.

## Troubleshooting

| Message or symptom | What to do |
| --- | --- |
| Python, Node.js, npm, or Chrome missing | Install the prerequisites above, then reopen the launcher. |
| Certificate verification failed | Follow the Python macOS installer's certificate setup instructions, then retry. |
| Port 5173 or 8000 is in use / app already running | Return to the previous Terminal window and press Ctrl+C. Do not run two copies. |
| Dependency installation failed | Check internet access and the Terminal error. Relaunch to retry. A successful setup is cached. |
| No usable release available | Download the release ZIP from Releases. From a source checkout, use `--local`. |
| Browser tab did not open | Open **http://localhost:5173** manually after the launcher says it is ready. |
| Could not open the Instagram browser | Check Chrome is installed in `/Applications` and another app instance is not using the profile. |
| Could not identify your profile | Finish login, use English, dismiss dialogs, and click Check connection again. |
| Publishing status unknown | Check the actual Instagram post before acknowledging the result. |

Keep error text when reporting a problem. Do not share your database, browser profile, credentials, or session secret.

## Run from source / develop the app

Requires the same macOS prerequisites. Clone this repository or download the source, open Terminal in its root folder, then run:

```sh
./InstaComment.command --local
```

This installs dependencies, starts the current checkout, and opens the workspace. It **does not download releases or overwrite your source**. Changes to dependency manifests trigger setup again. Local data stays in `backend/instacomment.db` and `backend/.local/`.

If dependencies are already installed, the existing development command is still available:

```sh
./scripts/start-local.sh
```

It starts both servers without opening the workspace automatically. Stop with Ctrl+C. After changing dependencies manually, reinstall them:

```sh
backend/.venv/bin/python -m pip install -r backend/requirements.txt
npm --prefix frontend ci
```

The app uses Node Playwright from `frontend/node_modules`; Python Playwright is not required. To use downloaded Chromium instead of Chrome with the development script:

```sh
npm --prefix frontend run browser:install
BROWSER_CHANNEL=chromium ./scripts/start-local.sh
```

### Demo mode

Start these in separate terminals from the repository root:

```sh
cd backend
MODE=demo FRONTEND_ORIGIN=http://localhost:5173 COOKIE_SECURE=false .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

```sh
cd frontend
npm run dev -- --port 5173 --strictPort
```

Demo mode simulates publishing, errors, and uncertain results; nothing is posted to Instagram. The launcher always starts real **local browser mode**. Old Vercel/Render configuration files are not deployment targets for this edition; Docker Compose is demo-only.

## Testing

From the repository root:

```sh
python3 -m unittest discover -s scripts/tests -p 'test_launcher.py' -v
python3 -m unittest discover -s scripts/tests -p 'test_launcher_smoke.py' -v
cd backend
.venv/bin/python -m pytest tests -q
cd ../frontend
npm test
npm run build
npm run test:browser-dom
npm run test:browser
npm run test:e2e
```

The launcher smoke test requires installed dependencies and free ports 5173/8000. It launches the packaged backend/frontend with temporary data, checks readiness, and shuts them down. It never opens Instagram or posts comments.

For desktop/mobile screenshots and console-error checks against an already-running frontend, use `npm run test:ui` from `frontend/`. These tests mock API calls; reports and screenshots go to `frontend/playwright-report/` and `frontend/test-results/`. The `test:e2e` command starts separate demo servers on ports 5175/8005. Real Instagram compatibility still requires your own manual verification.

## Publishing updates on GitHub

The [release workflow](.github/workflows/release.yml) runs on stable version tags such as `v1.0.0`. It checks the launcher, backend, frontend, and packaged server startup, then creates a GitHub Release containing **InstaComment-macOS.zip** and its SHA-256 checksum. The package includes app source and the launcher, never installed dependencies, local databases, browser profiles, or `.env` files.

After committing and pushing tested changes to `main`, a maintainer publishes a new version:

```sh
git tag v1.0.1
git push origin v1.0.1
```

Use a new version number each time; do not replace a published tag or its assets. The workflow can also be started manually with an existing stable tag. GitHub Actions needs permission to write repository contents for the release job; no personal access token is required. Releases must remain publicly downloadable for the unauthenticated launcher.

To inspect a package locally without publishing:

```sh
python3 scripts/package-release.py v1.0.1
```

The ZIP and checksum appear in ignored `release-dist/`. A release archive is platform-independent source; each Mac installs dependencies for its own architecture. Native signed `.app` packaging and Windows/Linux launchers are not included.

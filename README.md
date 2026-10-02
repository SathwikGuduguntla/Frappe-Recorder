### Frappe Recorder

Record your screen and camera from the browser, get a link straight away, and share it, in the style of [Kommodo](https://kommodo.ai/r) and Loom. Recordings can also be saved to a Google Drive folder of your choice.

The single-page app is served at `/recorder` and follows the frontend setup of [frappe/suite](https://github.com/frappe/suite): Vue 3, [frappe-ui](https://github.com/frappe/frappe-ui) and its Vite plugin, with a `www` page that boots the SPA.

#### Features

- **No account needed:** anyone can open `/recorder`, record and share. A visitor's recordings are tied to their browser: only that browser can rename or delete them, and its Library lists them. Logging in later moves them to the account. Administrators can switch this off or limit it (see below).
- **Recording modes:** screen + camera (with a camera bubble), screen only, or camera only
- **Audio:** microphone and computer/tab audio, mixed into one track; pick the camera and mic, with a live mic level meter
- **Controls:** 3-second countdown, pause/resume, mute, start over, cancel, and floating always-on-top controls (Document Picture-in-Picture in Chromium browsers) so you can stop the recording from any window
- **Instant link:** the video is uploaded in 3-second slices *while* you record. The share link exists from the first second and plays as soon as you stop. It is copied to your clipboard automatically.
- **Share page** (`/r/<id>`, which redirects to `/recorder/v/<id>`): video player, view count, emoji reactions, and time-stamped comments (guests can comment with a name). Link previews (Open Graph title and thumbnail) for chat apps.
- **Owner controls:** rename, description, private/public link, allow comments, allow downloads, delete
- **Library:** thumbnails, durations, views, comments, Drive status, search, folders
- **Google Drive:** connect your Google account, paste a Drive folder link, and every recording is uploaded there in the background (resumable uploads, any length). Optionally make the Drive copy viewable by anyone with the link, and optionally remove the copy from this site; the share page then plays the video from Drive.

#### Installation

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app frappe_recorder
bench build --app frappe_recorder
```

Open `https://your-site/recorder`. No login is required to record.

#### Recording without an account

In Desk, **Recorder Settings** controls recording by visitors who are not logged in:

- **Allow recording without logging in** (on by default). When off, `/recorder` sends people to the login page before recording.
- **Maximum size of a visitor's recording (MB)**, default 500. When reached, the recording stops and keeps what was recorded so far.
- **Recordings per hour from one IP address**, default 20.

Visitors' recordings are always public (anyone with the link can watch), because Frappe only serves private files to logged-in users. Their Google Drive copies go to the site's Drive folder, which a System Manager connects under **Recorder → Settings → Site settings**.

Requirements and notes:

- **HTTPS is required.** Browsers only allow screen and camera capture on secure origins (`https://` or `localhost`).
- **Background workers must be running** (`bench start` in development, supervisor in production). They fix up the video file and upload it to Drive.
- **`ffmpeg` (optional, recommended):** if it is installed on the server, finished recordings are re-muxed (no re-encoding) so the browser knows the video length up front. Without it, players still work but find the length on first play.
- Uploads are sent in small slices, so nginx's `client_max_body_size` and Frappe's upload size limit do not cap the recording length.

#### Google Drive setup

1. In [Google Cloud Console](https://console.cloud.google.com/apis/credentials), enable the **Google Drive API** and create an **OAuth client ID** of type *Web application*.
2. Add `https://your-site/api/method/frappe_recorder.api.drive.oauth_callback` as an **Authorized redirect URI**.
3. In Desk, open **Google Drive Settings**, tick **Enable Google Drive Storage**, and paste the client ID and secret.
4. Each user then opens **Recorder → Settings**, clicks **Connect Google Drive**, and pastes the link of the Drive folder their recordings should go to.
5. For recordings made without logging in, a System Manager connects the site's Drive account and folder in the same place, under **Site settings**.

The app asks for the `drive` scope because it uploads into a folder you choose by link. The narrower `drive.file` scope only sees folders the app created itself. While the OAuth consent screen is in *Testing* mode, add your users as test users.

#### Development

```bash
cd apps/frappe_recorder/frontend
yarn
yarn dev   # proxies /api, /files, /login… to your bench
```

`yarn build` writes the bundle to `frappe_recorder/public/frontend` and the page to `frappe_recorder/www/recorder.html` (both git-ignored; `bench build` regenerates them).

Server code:

- `frappe_recorder/api/recording.py`: create, chunked upload, finalize, share page data, comments, folders
- `frappe_recorder/api/drive.py`: Google OAuth, folder link validation, resumable Drive upload
- `frappe_recorder/www/recorder.py`: boots the SPA and adds link-preview tags

Run the tests with `bench --site <site> run-tests --app frappe_recorder`.

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/frappe_recorder
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### CI

This app can use GitHub Actions for CI. The following workflows are configured:

- CI: Installs this app and runs unit tests on every push to `develop` branch.
- Linters: Runs [Frappe Semgrep Rules](https://github.com/frappe/semgrep-rules) and [pip-audit](https://pypi.org/project/pip-audit/) on every pull request.

### License

agpl-3.0

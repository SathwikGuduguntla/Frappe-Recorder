### Frappe Recorder

Record your screen, your camera, or both in the browser and get a share link the moment you stop.

- **Record** at `/recorder`: Screen + Camera (camera shown as a bubble), Screen only, or Camera only, with microphone and system audio, a 3-second countdown, pause/resume, mute and discard.
- **Share** at `/r/<token>`: anyone with the link can watch, no sign-in. The owner can rename, switch link sharing off, download and delete. Views are counted.
- **Library** at `/recorder/library`: all of your recordings with thumbnails and search.
- **Google Drive** at `/recorder/settings`: paste a Drive folder link and connect a Google account; every recording is then copied into that folder, and videos already in the folder can be imported into the library.

The video is uploaded in small pieces while you record, so the link is ready as soon as you press stop, however long the recording is.

#### Google Drive setup

1. In [Google Cloud Console](https://console.cloud.google.com/) enable the **Google Drive API** and create an OAuth client of type **Web application**.
2. Open `/recorder/settings` as a System Manager. Copy the redirect URI shown there into the OAuth client's *Authorized redirect URIs*.
3. Paste the client ID and secret, and the link of the Drive folder to store recordings in. Save.
4. Press **Connect Google Drive** and sign in with an account that can add files to that folder.
5. Turn on **Google Drive storage**.

Uploads run in the background queue (`long`), so a worker must be running. Failed uploads are retried hourly.

The app asks Google for the full `drive` scope, because it writes into a folder you choose by link. Until the OAuth app is verified by Google, add the connecting account as a test user on the consent screen.

#### Notes

- Recording needs a signed-in user. Watching a shared link does not.
- Video files are stored in `private/files/recorder` and served through `frappe_recorder.api.stream`, so turning link sharing off really does cut access.
- Deleting a recording removes it from this site. The copy in Google Drive is kept.

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app frappe_recorder
bench build --app frappe_recorder
```

#### Frontend development

```bash
cd apps/frappe_recorder/frontend
yarn install
yarn dev
```

Then open `http://<your-site>:8080/recorder`. Add `"ignore_csrf": 1` to the site config while using the dev server.

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

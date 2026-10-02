### Frappe Recorder

Record your screen, your camera, or both in the browser and get a share link the moment you stop.

- **Record** at `/recorder`: Screen + Camera (camera shown as a bubble), Screen only, or Camera only, with microphone and system audio, a 3-second countdown, pause/resume, mute and discard.
- **Share** at `/r/<token>`: anyone with the link can watch, no sign-in. The owner can rename, switch link sharing off, download and delete. Views are counted.
- **Library** at `/recorder/library`: all of your recordings with thumbnails and search.
- **Google Drive** at `/recorder/settings`: paste the link of a Drive folder shared as *Anyone with the link → Editor*; every recording is then copied into that folder, and videos already in the folder can be imported into the library.

The video is uploaded in small pieces while you record, so the link is ready as soon as you press stop, however long the recording is.

#### Google Drive setup

No Google Cloud project, OAuth client or "Connect" step is needed.

1. In Google Drive, open the folder's **Share** dialog and set General access to **Anyone with the link**, role **Editor**. Copy the link (for example `https://drive.google.com/drive/folders/1ugelp0xHEjC-VTsvphwSai4aUfYEQ0HT?usp=sharing`).
2. Open `/recorder/settings` as a System Manager and paste it into **Drive folder link**.
3. One time only, set up the **Uploader**. Google only accepts uploads made by a Google account, even into a public folder, so a small Apps Script uploads as your account:
   - open a new project at [script.google.com/create](https://script.google.com/create);
   - paste the script shown on the settings page (it already contains this site's secret) and save;
   - **Deploy → New deployment → Web app**, with *Execute as: Me* and *Who has access: Anyone*. Allow access when Google asks; if it says the app isn't verified, choose **Advanced → Go to (project name)**, since it is your own script;
   - paste the **Web app URL** into the settings page.
4. Save. The recorder checks the uploader and the folder straight away and turns Drive storage on.

Uploads run in the background queue (`long`), so a worker must be running. Failed uploads are retried hourly. Videos are uploaded as the Google account that deployed the script, and use its storage quota.

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

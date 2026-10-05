### Frappe Recorder

Record your screen, your camera, or both in the browser and get a share link the moment you stop.

- **Record** at `/recorder`: Screen + Camera (camera shown as a bubble), Screen only, or Camera only, with microphone and system audio, a 3-second countdown, pause/resume, mute and discard.
- **Share** at `/r/<token>`: anyone with the link can watch, no sign-in. The owner can rename, switch link sharing off, download and delete. Views are counted.
- **Library** at `/recorder/library`: all of your recordings with thumbnails and search.
- **Google Drive** at `/recorder/settings`: sign in with Google and paste a folder link; every recording is then copied into that folder, and videos already in the folder can be imported into the library.
- **Transcript and AI notes** on every video: a timestamped transcript, a summary, highlights and a step-by-step SOP, with clickable times that jump the video. Made by free open-source models in the recording owner's browser: no API key, no server load, works on any hosting plan.

The video is uploaded in small pieces while you record, so the link is ready as soon as you press stop, however long the recording is.

#### Google Drive setup

Open `/recorder/settings` as a System Manager and connect the Google account that should own the videos, in one of two ways:

- **Sign in with Google.** Click **Connect Google Drive** and allow access. This needs an OAuth client, added once: in [Google Cloud Console](https://console.cloud.google.com/apis/library/drive.googleapis.com) enable the **Google Drive API** (set up the consent screen if asked; while it is in testing, add your account as a test user), [create an OAuth client ID](https://console.cloud.google.com/apis/credentials) of type **Web application** with the redirect URI shown on the settings page (`https://<your-site>/api/method/frappe.integrations.google_oauth.callback`), and paste the Client ID and secret into the settings page. They are saved in Frappe's Google Settings, so skip this if that already has a client.
- **Apps Script** (no Google Cloud project): open [script.google.com/create](https://script.google.com/create) with that account, paste the script shown on the settings page (it already contains this site's secret) and save; **Deploy → New deployment → Web app** with *Execute as: Me* and *Who has access: Anyone*, allow access (if Google says the app isn't verified, choose **Advanced → Go to (project name)**); paste the **Web app URL** into the settings page and click **Connect**.

  To check an Apps Script deployment, open the Web app URL in a private browser window: it should show `"The uploader is running."`. A Google sign-in page means *Who has access* is not **Anyone** (Google Workspace admins can turn that option off; deploy from a personal Gmail account then). After editing the script, deploy it again with **Deploy → Manage deployments → Edit → Version: New version**, since a deployment keeps the code it was made with.

Then paste the link of a Drive folder that account can add files to, and save. Drive storage turns on.

Uploads run in the background queue (`long`), so a worker must be running. Failed uploads are retried hourly. Videos are uploaded as the connected Google account and use its storage quota.

#### Transcripts and AI notes

On by default, under **Transcripts and AI notes** in `/recorder/settings`. Nothing to install on the server.

- When the owner opens a finished recording, their browser transcribes it with **Whisper** ([transformers.js](https://github.com/huggingface/transformers.js)) and saves the transcript.
- The summary, highlights and SOP are written in the same browser by a small open-source model (**Qwen2.5** or **Llama 3.2** through [WebLLM](https://github.com/mlc-ai/web-llm)). This needs WebGPU: Chrome or Edge on a computer with a graphics card. If the model is already downloaded, the summary starts by itself; otherwise the owner clicks **Write summary**.
- Models are downloaded once from Hugging Face and kept in the browser's cache. Whisper base is about 145 MB; Qwen2.5 1.5B is about 1 GB.
- Viewers just read the results, on any device.

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

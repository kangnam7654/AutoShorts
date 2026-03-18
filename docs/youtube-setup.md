# YouTube Upload Setup

MoneyPrinter can upload generated videos directly to YouTube. This requires a one-time OAuth2 setup.

## 1. Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or use an existing one)
3. Enable the **YouTube Data API v3**:
   - Navigate to **APIs & Services > Library**
   - Search for "YouTube Data API v3"
   - Click **Enable**

## 2. Create OAuth2 Credentials

1. Go to **APIs & Services > Credentials**
2. Click **Create Credentials > OAuth client ID**
3. If prompted, configure the OAuth consent screen:
   - User Type: **External**
   - Fill in app name, email
   - Add scope: `https://www.googleapis.com/auth/youtube.upload`
   - Add yourself as a test user
4. Application type: **Desktop app**
5. Download the JSON file

## 3. Place the Credentials File

Rename the downloaded file and place it in the Backend directory:

```bash
mv ~/Downloads/client_secret_XXXXX.json Backend/client_secret.json
```

This file is gitignored and will not be committed.

## 4. Authenticate

Run the auth command:

```bash
uv run python Backend/cli.py auth
```

This opens a browser window for Google sign-in. After authorization, a token file (`Backend/youtube-oauth2.json`) is created automatically.

## 5. Upload Videos

Add `--upload` to any generation command:

```bash
uv run python Backend/cli.py veo \
  --prompt-file prompts.json \
  --image character.png \
  --upload \
  --upload-title "My Video Title" \
  -o output/video.mp4
```

## Token Refresh

The OAuth token refreshes automatically. If you encounter 401 errors, re-run `cli.py auth`.

## Troubleshooting

### "Access blocked: This app's request is invalid"
Your OAuth consent screen is likely not configured. Go to **APIs & Services > OAuth consent screen** and complete the setup.

### "Quota exceeded"
YouTube Data API has a daily quota. Default is 10,000 units; an upload costs 1,600 units. You can upload about 6 videos per day with the default quota.

### Upload succeeds but video is "private"
New OAuth apps are in testing mode. Videos uploaded by test users default to private. To change this, publish your OAuth consent screen or set `privacy_status='unlisted'` in the upload call.

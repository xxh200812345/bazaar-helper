# BazaarHelper Auto Update

BazaarHelper uses a small external PowerShell updater. The app keeps user data in
`%LOCALAPPDATA%\BazaarHelper\runtime`, so replacing the application folder does
not overwrite API keys or runtime game state.

## Release Flow

1. Update `VERSION`.
2. Build the normal release folder:

   ```powershell
   .\package_release.ps1
   ```

3. Create the update zip and manifest:

   ```powershell
   .\scripts\make_update_package.ps1 -DownloadBaseUrl "https://example.com/BazaarHelper"
   ```

4. Upload these files from `releases\`:

   ```text
   BazaarHelper-<version>.zip
   latest.json
   ```

5. Configure installed clients with:

   ```text
   BAZAAR_HELPER_UPDATE_MANIFEST_URL=https://example.com/BazaarHelper/latest.json
   ```

   Or put the manifest URL in `update_url.txt` next to `start.bat`.

## Manifest Format

```json
{
  "name": "BazaarHelper",
  "version": "0.1.0",
  "url": "https://example.com/BazaarHelper/BazaarHelper-0.1.0.zip",
  "sha256": "lowercase sha256 hash",
  "notes": "",
  "published_at": "2026-07-02T00:00:00Z"
}
```

The updater requires `version`, `url`, and `sha256`. It downloads the zip,
verifies the SHA256 hash, backs up the current app folder, stops
`BazaarHelper.exe`, copies the new files over the app folder, and attempts a
rollback if copying fails.

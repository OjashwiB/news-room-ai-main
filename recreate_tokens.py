import sys
import pickle
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

print("=" * 60)
print("Google OAuth Token Recreation Script")
print("Defy Logic Newsroom AI")
print("=" * 60)

creds_dir = Path("credentials")
creds_dir.mkdir(exist_ok=True)
print(f"Credentials directory: {creds_dir.absolute()}")

from config.settings import settings

token_path = Path("credentials/youtube_token.pickle")
secrets_path = Path(settings.YOUTUBE_CLIENT_SECRETS_PATH)

print(f"\nClient secrets: {secrets_path}")
print(f"Token file:     {token_path}")

if not secrets_path.exists():
    print(f"\nERROR: YouTube client secrets not found at: {secrets_path}")
    print("  1. Go to Google Cloud Console → APIs & Services → Credentials")
    print("  2. Create an OAuth 2.0 Client ID (Desktop app)")
    print("  3. Download the JSON and save it to:", secrets_path)
    sys.exit(1)

# Delete existing token to force a fresh auth with the current scope
if token_path.exists():
    token_path.unlink()
    print("\nExisting token deleted — will re-authenticate with current scope.")

print("\n" + "=" * 60)
print("Authenticating YouTube...")
print("  Scope: youtube.force-ssl (uploads + thumbnails + playlists)")
print("  A browser window will open for Google sign-in.")
print("=" * 60)

results = {"youtube": False}

try:
    from tools.youtube_tool import _get_youtube_service

    youtube = _get_youtube_service()
    print("YouTube authentication successful!")
    print(f"Token saved to: {token_path}")

    # Verify with a lightweight API call
    response = youtube.channels().list(part="snippet", mine=True).execute()
    items = response.get("items", [])
    if items:
        channel_name = items[0]["snippet"]["title"]
        print(f"Channel verified: {channel_name}")
    else:
        print("Auth succeeded (no channel found on this account).")

    results["youtube"] = True

except Exception as e:
    print(f"YouTube authentication failed: {e}")

print("\n" + "=" * 60)
print("Authentication Summary")
print("=" * 60)

success_count = sum(results.values())
total_count = len(results)

for service, success in results.items():
    status = "SUCCESS" if success else "FAILED"
    print(f"{service.upper():12} : {status}")

print("\n" + "=" * 60)
if success_count == total_count:
    print(f"All {total_count} service(s) authenticated successfully!")
else:
    print("Authentication failed.")
    print("  Check the error message above and verify your client secrets file.")
print("=" * 60)

print("\nToken file location: credentials/youtube_token.pickle")
print("\nYou can now start the newsroom with: python main.py")

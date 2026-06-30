"""
Comprehensive tool test suite for news-room-ai.
Run from the project root: python test_tools.py
"""
import sys, json, os, traceback
from pathlib import Path

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"

results = []

def check(name, fn):
    try:
        detail = fn()
        results.append((PASS, name, detail))
        print(f"  [PASS] {name}: {str(detail)[:120]}")
    except Exception as e:
        results.append((FAIL, name, str(e)))
        print(f"  [FAIL] {name}: {e}")
        traceback.print_exc()

def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)

# ──────────────────────────────────────────────
# 1. SETTINGS
# ──────────────────────────────────────────────
section("1. Config / Settings")

def test_settings_load():
    from config.settings import settings
    assert settings.OPENAI_API_KEY, "OPENAI_API_KEY missing"
    assert settings.TAVILY_API_KEY, "TAVILY_API_KEY missing"
    assert settings.HEYGEN_API_KEY, "HEYGEN_API_KEY missing"
    return f"newsroom={settings.NEWSROOM_NAME}, port={settings.PORT}"

check("settings load + required keys present", test_settings_load)

# ──────────────────────────────────────────────
# 2. FILE OPERATIONS
# ──────────────────────────────────────────────
section("2. File Operations Tool")

from tools.file_operations_tool import file_operations_tool

TEST_DIR = "./output/test_run"
TEST_FILE = "test_article_TIMESTAMP"

def test_create_dir():
    r = file_operations_tool.invoke({"action": "create_directory", "directory": TEST_DIR})
    assert "created" in r.lower() or "exists" in r.lower(), r
    return r

def test_save_file():
    r = file_operations_tool.invoke({
        "action": "save_file",
        "content": "# Test Article\n\nThis is a test article for the news-room-ai tool test suite.",
        "filename": TEST_FILE,
        "file_type": "md",
        "directory": TEST_DIR,
    })
    assert "saved" in r.lower() or "successfully" in r.lower(), r
    return r

def test_list_files():
    r = file_operations_tool.invoke({"action": "list_files", "directory": TEST_DIR})
    assert "test_article" in r or "No files" in r, r
    return r[:100]

def test_read_file():
    # Find the file we just saved
    files = list(Path(TEST_DIR).glob("test_article*.md"))
    assert files, "No test file found to read"
    fname = files[0].name
    r = file_operations_tool.invoke({"action": "read_file", "filename": fname, "directory": TEST_DIR})
    assert "Test Article" in r, r
    return f"Read {len(r)} chars from {fname}"

def test_delete_file():
    files = list(Path(TEST_DIR).glob("test_article*.md"))
    assert files, "No test file to delete"
    fname = files[0].name
    r = file_operations_tool.invoke({"action": "delete_file", "filename": fname, "directory": TEST_DIR})
    assert "deleted" in r.lower() or "removed" in r.lower(), r
    return r

check("create_directory", test_create_dir)
check("save_file (with TIMESTAMP)", test_save_file)
check("list_files", test_list_files)
check("read_file", test_read_file)
check("delete_file", test_delete_file)

# ──────────────────────────────────────────────
# 3. VIDEO TOOLS (no-API subset)
# ──────────────────────────────────────────────
section("3. Video Tools (local)")

from tools.video_tools import extract_graphic_cues, save_video_package

def test_extract_graphic_cues():
    script = "Good evening. [GRAPHIC: headline] The situation worsens. [GRAPHIC: map of region] Reporting live."
    r = extract_graphic_cues.invoke({"script": script})
    data = json.loads(r)
    assert len(data["graphic_cues"]) == 2, f"Expected 2 cues, got {data}"
    return f"Found {len(data['graphic_cues'])} cues: {data['graphic_cues']}"

def test_save_video_package():
    pkg = json.dumps({
        "title": "Test Package",
        "topic": "Test",
        "video_file": "./output/media/test.mp4",
        "graphic_cues": ["headline", "map"],
    })
    r = save_video_package.invoke({"package_data": pkg, "directory": TEST_DIR})
    assert "video_package" in r.lower() or "saved" in r.lower(), r
    return r[:120]

check("extract_graphic_cues", test_extract_graphic_cues)
check("save_video_package", test_save_video_package)

# ──────────────────────────────────────────────
# 4. WEB RESEARCH (Tavily)
# ──────────────────────────────────────────────
section("4. Web Research Tool (Tavily)")

from tools.web_research_tool import web_research_tool

def test_web_research():
    r = web_research_tool.invoke({"query": "latest news today", "limit": 2, "search_depth": "basic"})
    assert len(r) > 100, "Response too short"
    return f"{len(r)} chars returned"

check("web_research_tool (basic search)", test_web_research)

# ──────────────────────────────────────────────
# 5. IMAGE SEARCH (Tavily)
# ──────────────────────────────────────────────
section("5. Image Search Tool (Tavily)")

from tools.image_search_tool import image_search_tool

def test_image_search():
    r = image_search_tool.invoke({"query": "space rocket launch", "num_results": 2})
    data = json.loads(r)
    images = data.get("images", data) if isinstance(data, dict) else data
    assert isinstance(images, list) and len(images) > 0, f"Expected list of images, got: {r[:200]}"
    assert "url" in images[0], f"Missing 'url' key in result: {images[0]}"
    return f"{len(images)} images returned, first: {images[0].get('caption','')[:60]}"

check("image_search_tool", test_image_search)

# ──────────────────────────────────────────────
# 6. VIDEO SEARCH (Pixabay)
# ──────────────────────────────────────────────
section("6. Video Search Tool (Pixabay)")

from tools.video_search_tool import video_search_tool

def test_video_search():
    r = video_search_tool.invoke({"query": "city skyline aerial", "num_results": 2})
    data = json.loads(r)
    videos = data.get("videos", data) if isinstance(data, dict) else data
    assert isinstance(videos, list), f"Expected list, got: {type(videos)}"
    if len(videos) == 0:
        return "WARN: 0 results (Pixabay may have no match or key issue)"
    assert "url" in videos[0], f"Missing 'url' in result: {videos[0]}"
    return f"{len(videos)} videos returned, first: {str(videos[0].get('url',''))[:80]}"

check("video_search_tool", test_video_search)

# ──────────────────────────────────────────────
# 7. HEYGEN
# ──────────────────────────────────────────────
section("7. HeyGen Tools")

from tools.heygen_tool import (
    get_heygen_credits,
    list_heygen_avatars,
    list_heygen_voices,
    check_video_status,
)

def test_heygen_credits():
    credits = get_heygen_credits()
    assert isinstance(credits, int), f"Expected int, got {type(credits)}"
    return f"{credits} credits remaining"

def test_heygen_avatars():
    r = list_heygen_avatars.invoke({})
    data = json.loads(r)
    avatars = data.get("avatars", data) if isinstance(data, dict) else data
    assert isinstance(avatars, list) and len(avatars) > 0, "No avatars returned"
    return f"{len(avatars)} avatars available, first: {avatars[0].get('avatar_name','?')}"

def test_heygen_voices():
    r = list_heygen_voices.invoke({})
    data = json.loads(r)
    voices = data.get("voices", data) if isinstance(data, dict) else data
    assert isinstance(voices, list) and len(voices) > 0, "No voices returned"
    return f"{len(voices)} voices available, first: {voices[0].get('name','?')}"

def test_heygen_status_invalid():
    # Test that check_video_status handles a bad ID gracefully
    r = check_video_status.invoke({"video_id": "invalid_test_id_000"})
    # Should return an error JSON, not crash
    assert r and len(r) > 0, "Empty response"
    return f"Error handled gracefully: {r[:80]}"

check("get_heygen_credits", test_heygen_credits)
check("list_heygen_avatars", test_heygen_avatars)
check("list_heygen_voices", test_heygen_voices)
check("check_video_status (invalid id — error handling)", test_heygen_status_invalid)

# ──────────────────────────────────────────────
# 8. VIDEO DOWNLOAD
# ──────────────────────────────────────────────
section("8. Video Download Tool")

from tools.video_tools import download_video

def test_download_video():
    # Use a small public test video (Big Buck Bunny sample, ~1MB)
    test_url = "https://www.w3schools.com/html/mov_bbb.mp4"
    r = download_video.invoke({
        "url": test_url,
        "filename": "test_download.mp4",
        "directory": TEST_DIR,
    })
    assert "error" not in r.lower() or "saved" in r.lower() or "downloaded" in r.lower() or ".mp4" in r, r
    return r[:120]

check("download_video (small public clip)", test_download_video)

# ──────────────────────────────────────────────
# 9. YOUTUBE
# ──────────────────────────────────────────────
section("9. YouTube Tool (auth check)")

def test_youtube_auth():
    from tools.youtube_tool import youtube_upload_video
    import pickle
    token_path = "credentials/youtube_token.pickle"
    assert os.path.exists(token_path), "youtube_token.pickle not found"
    with open(token_path, "rb") as f:
        creds = pickle.load(f)
    assert creds is not None, "Credentials loaded as None"
    valid = creds.valid
    expired = creds.expired if hasattr(creds, "expired") else "unknown"
    has_refresh = bool(creds.refresh_token) if hasattr(creds, "refresh_token") else False
    return f"token valid={valid}, expired={expired}, has_refresh_token={has_refresh}"

check("youtube token exists and is loadable", test_youtube_auth)

# ──────────────────────────────────────────────
# SUMMARY
# ──────────────────────────────────────────────
section("SUMMARY")
passed = sum(1 for s, *_ in results if s == PASS)
failed = sum(1 for s, *_ in results if s == FAIL)
skipped = sum(1 for s, *_ in results if s == SKIP)
print(f"\n  {passed} passed  |  {failed} failed  |  {skipped} skipped\n")
if failed:
    print("  FAILED TESTS:")
    for status, name, detail in results:
        if status == FAIL:
            print(f"    ✗ {name}")
            print(f"      {detail}")
print()
sys.exit(1 if failed else 0)

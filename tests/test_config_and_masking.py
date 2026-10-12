import pytest
from app.config import (
    mask_secret,
    REGEX_DISCORD_WEBHOOK,
    REGEX_FB_GROUP_URL,
    REGEX_MENTION_TAG,
    REGEX_GEMINI_MODEL
)

def test_masking_rule():
    # length <= 8 -> fixed "••••••••"
    assert mask_secret("") == ""
    assert mask_secret("1234") == "••••••••"
    assert mask_secret("12345678") == "••••••••"

    # length > 8 -> "••••••••" + last 4 characters
    assert mask_secret("123456789") == "••••••••6789"
    assert mask_secret("AIzaSyD-1234567890abcdef") == "••••••••cdef"
    assert mask_secret("https://discord.com/api/webhooks/123/xyz") == "••••••••/xyz"

def test_discord_webhook_regex():
    valid = [
        "https://discord.com/api/webhooks/123456789012345678/abcdefg-hijklmn_opqrst",
        "https://canary.discord.com/api/webhooks/987654321/token123",
        "https://ptb.discord.com/api/webhooks/555555555/token_456"
    ]
    for url in valid:
        assert bool(REGEX_DISCORD_WEBHOOK.match(url)), f"Failed on valid: {url}"

    invalid = [
        "https://discordapp.com/api/webhooks/123/token",
        "http://discord.com/api/webhooks/123/token",
        "https://google.com",
        "https://discord.com/channels/123/456"
    ]
    for url in invalid:
        assert not bool(REGEX_DISCORD_WEBHOOK.match(url)), f"Failed to reject: {url}"

def test_fb_group_regex():
    valid = [
        "https://www.facebook.com/groups/1004107450379879/",
        "https://facebook.com/groups/chomaytinhcu",
        "https://www.facebook.com/groups/manhinh.gaming/",
    ]
    for url in valid:
        assert bool(REGEX_FB_GROUP_URL.match(url)), f"Failed on valid: {url}"

    invalid = [
        "https://facebook.com/user/123",
        "https://www.facebook.com/fanpage.name",
        "https://google.com/groups/123",
        "https://facebook.com/groups/123/posts/456",  # Post URL, not group
        "http://facebook.com/groups/123"
    ]
    for url in invalid:
        assert not bool(REGEX_FB_GROUP_URL.match(url)), f"Failed to reject: {url}"

def test_mention_tag_regex():
    valid = ["", "@everyone", "@here", "<@&123456789>", "<@987654321>"]
    for tag in valid:
        assert bool(REGEX_MENTION_TAG.match(tag)), f"Failed on valid: {tag}"

    invalid = ["everyone", "@all", "<@role>", "<random>"]
    for tag in invalid:
        assert not bool(REGEX_MENTION_TAG.match(tag)), f"Failed to reject: {tag}"

def test_gemini_model_regex():
    assert bool(REGEX_GEMINI_MODEL.match("gemini-3.5-flash"))
    assert bool(REGEX_GEMINI_MODEL.match("gemini-1.5-pro-latest"))
    assert not bool(REGEX_GEMINI_MODEL.match("gemini/model;rm -rf"))

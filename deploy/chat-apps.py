"""The app each agent needs in Teams or Slack, made from what a5s takes, so nobody works out its
scopes, events and addresses by hand (docs/first-day.md#3-the-chat).

Teams: an app package to upload, in the Teams admin center or as a custom app, for a bot already
registered in the tenant's Entra ID, whose messaging endpoint is
https://<host>/channels/teams/messages. It holds the manifest, in the personal and group chat
scopes only, since a5s turns a team's channels away, with files on, and two plain icons to
replace with your own:

    python3 deploy/chat-apps.py teams --agent assistant --app-id <its bot's app id> \\
        --host a5s.example.org --developer "Example Ltd" --out assistant.zip

Slack: an app manifest, which "Create New App", "From a manifest" takes, with the bot's scopes,
its events sent to https://<host>/channels/slack/events, its buttons to
https://<host>/channels/slack/actions, and Socket Mode and token rotation off, as a5s needs:

    python3 deploy/chat-apps.py slack --agent assistant --host a5s.example.org > assistant.yaml

It needs Python 3.10 or later, and nothing else. Make one app for each agent, so each talks to
people as itself."""

from __future__ import annotations

import argparse
import json
import struct
import sys
import zipfile
import zlib

# What a5s takes from each chat (a5s/core/teams.py, a5s/core/slack.py, README.md#chats)
TEAMS_ENDPOINT = "/channels/teams/messages"
SLACK_EVENTS = "/channels/slack/events"
SLACK_ACTIONS = "/channels/slack/actions"
SLACK_SCOPES = ("app_mentions:read", "channels:read", "chat:write", "files:read", "groups:read",
                "im:history", "im:read", "im:write", "mpim:history", "mpim:read",
                "reactions:read", "users:read")
SLACK_EVENTS_SENT = ("app_mention", "message.im", "message.mpim", "reaction_added")
TEAMS_SCHEMA = "1.17"
OCEAN = "#0369A1"  # Ocean's accent, --ocean-600, which a5s's pages wear


def png(size: int, fill: tuple[int, int, int, int], ring: int = 0) -> bytes:
    """A square PNG of one colour, or, with `ring`, a ring of it that wide on clear: Teams asks
    for a colour icon and an outline one, which you replace with your own."""
    def pixel(x: int, y: int) -> bytes:
        edge = min(x, y, size - 1 - x, size - 1 - y)
        return bytes(fill) if not ring or edge < ring else b"\0\0\0\0"

    rows = b"".join(b"\0" + b"".join(pixel(x, y) for x in range(size)) for y in range(size))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)  # 8 bits a channel, RGBA
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(rows))
            + chunk(b"IEND", b""))


def teams(agent: str, app_id: str, host: str, developer: str, name: str, about: str) -> dict:
    """The manifest of an agent's Teams app, for the bot registered as `app_id`."""
    site = f"https://{host}/"
    return {
        "$schema": "https://developer.microsoft.com/json-schemas/teams/"
                   f"v{TEAMS_SCHEMA}/MicrosoftTeams.schema.json",
        "manifestVersion": TEAMS_SCHEMA,
        "version": "1.0.0",
        "id": app_id,
        "developer": {"name": developer, "websiteUrl": site, "privacyUrl": site,
                      "termsOfUseUrl": site},
        "name": {"short": name[:30], "full": f"{name}, an a5s agent"[:100]},
        "description": {"short": about[:80], "full": about[:4000]},
        "icons": {"color": "color.png", "outline": "outline.png"},
        "accentColor": OCEAN,
        "bots": [{"botId": app_id, "scopes": ["personal", "groupChat"], "supportsFiles": True,
                  "isNotificationOnly": False}],
        "permissions": ["identity", "messageTeamMembers"],
        "validDomains": [host],
    }


def slack(agent: str, host: str, name: str, about: str) -> str:
    """The manifest of an agent's Slack app, as YAML, which Slack takes."""
    scopes = "\n".join(f"      - {s}" for s in SLACK_SCOPES)
    events = "\n".join(f"      - {e}" for e in SLACK_EVENTS_SENT)
    return f"""display_information:
  name: {json.dumps(name[:35])}
  description: {json.dumps(about[:140])}
features:
  app_home:
    home_tab_enabled: false
    messages_tab_enabled: true
    messages_tab_read_only_enabled: false  # people write to it from its Messages tab
  bot_user:
    display_name: {json.dumps(agent[:80])}
    always_online: true
oauth_config:
  scopes:
    bot:
{scopes}
settings:
  event_subscriptions:
    request_url: https://{host}{SLACK_EVENTS}
    bot_events:
{events}
  interactivity:
    is_enabled: true
    request_url: https://{host}{SLACK_ACTIONS}
  org_deploy_enabled: false
  socket_mode_enabled: false
  token_rotation_enabled: false  # a5s doesn't renew a bot token
"""


def main(argv: list[str] | None = None) -> int:
    given = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    chats = given.add_subparsers(dest="chat", required=True)
    for chat in ("teams", "slack"):
        made = chats.add_parser(chat)
        made.add_argument("--agent", required=True, help="the agent, such as assistant")
        made.add_argument("--host", required=True, help="where people reach a5s, such as "
                                                        "a5s.example.org")
        made.add_argument("--name", help="what people see it called (default: the agent's name)")
        made.add_argument("--about", help="what it does, in a sentence")
        if chat == "teams":
            made.add_argument("--app-id", required=True, help="its bot's app id, from Entra ID")
            made.add_argument("--developer", required=True, help="the organisation, as Teams "
                                                                 "shows who made it")
            made.add_argument("--out", required=True, help="the package to write, such as "
                                                           "assistant.zip")
    args = given.parse_args(argv)
    host = args.host.removeprefix("https://").rstrip("/")
    name = args.name or args.agent.replace("-", " ").capitalize()
    about = args.about or f"{name}, an agent a5s runs for your organisation."
    if args.chat == "slack":
        sys.stdout.write(slack(args.agent, host, name, about))
        return 0
    manifest = teams(args.agent, args.app_id, host, args.developer, name, about)
    with zipfile.ZipFile(args.out, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr("manifest.json", json.dumps(manifest, indent=2) + "\n")
        package.writestr("color.png", png(192, (3, 105, 161, 255)))
        package.writestr("outline.png", png(32, (255, 255, 255, 255), ring=3))
    print(f"Wrote {args.out}: upload it in the Teams admin center, as a custom app, once its bot "
          f"is registered with its messaging endpoint at https://{host}{TEAMS_ENDPOINT}. "
          "Replace its two icons with your own first, if you like.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

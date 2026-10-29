"""Configure the development stack's Matrix homeserver, Synapse, with new secrets.

Writes its settings, its signing key, and a5s's registration as an application
service into a folder, and prints where they are and the two tokens a5s needs,
for compose's environment:

    python3 deploy/matrix/configure.py .a5s/matrix >> .a5s/compose.env

The homeserver federates with nobody, and turns encryption off by default, so a5s
can read people's direct chats. It's for test and development only: a real one is
the organisation's own, with a5s registered on it the same way.
"""

import base64
import secrets
import sys
from pathlib import Path

SERVER = "a5s.test"  # the sample's people are @ana:a5s.test and so on, in its directory


def main(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    folder.chmod(0o755)
    as_token, hs_token = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    seed = base64.b64encode(secrets.token_bytes(32)).decode().rstrip("=")
    files = {
        "signing.key": f"ed25519 a_a5s {seed}\n",
        "homeserver.yaml": f"""\
server_name: {SERVER}
pid_file: /data/homeserver.pid
listeners:
  - port: 8008
    type: http
    bind_addresses: ["0.0.0.0"]
    tls: false
    x_forwarded: true
    resources: [{{names: [client], compress: false}}]
database: {{name: sqlite3, args: {{database: /data/homeserver.db}}}}
media_store_path: /data/media_store
signing_key_path: /config/signing.key
report_stats: false
trusted_key_servers: []
suppress_key_server_warning: true
federation_domain_whitelist: []
enable_registration: false
registration_shared_secret: {secrets.token_urlsafe(32)}
macaroon_secret_key: {secrets.token_urlsafe(32)}
form_secret: {secrets.token_urlsafe(32)}
encryption_enabled_by_default_for_room_type: "off"
app_service_config_files: [/config/a5s.yaml]
""",
        "a5s.yaml": f"""\
# a5s, as an application service: the homeserver sends it what happens in its
# bots' rooms, and it speaks as its bots, @a5s-<agent>:{SERVER}.
id: a5s
url: http://channels:8703/channels/matrix
as_token: {as_token}
hs_token: {hs_token}
sender_localpart: a5s
rate_limited: false
namespaces:
  users: [{{exclusive: true, regex: "@a5s-.*:{SERVER.replace('.', chr(92) * 2 + '.')}"}}]
  aliases: []
  rooms: []
""",
    }
    for name, text in files.items():
        (folder / name).write_text(text)
        (folder / name).chmod(0o644)  # Synapse reads them as its own user
    print(f"A5S_MATRIX_CONFIG={folder.resolve()}\nA5S_MATRIX_AS_TOKEN={as_token}\n"
          f"A5S_MATRIX_HS_TOKEN={hs_token}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))

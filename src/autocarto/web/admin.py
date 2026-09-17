"""Private-beta administration: migrate DB, create invitations, revoke sessions."""
import argparse
from pathlib import Path
from sqlalchemy import delete, select
from .store import get_store, sessions, users


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate")
    invite = sub.add_parser("invite")
    invite.add_argument("--email", required=True)
    invite.add_argument("--output", type=Path, required=True, help="Write the single-use secret to a private file, never logs")
    revoke = sub.add_parser("revoke-sessions")
    revoke.add_argument("--email", required=True)
    args = parser.parse_args()
    store = get_store()
    if args.command == "migrate":
        store.migrate()
        print("Database schema v1 ready")
    elif args.command == "invite":
        if "@" not in args.email or len(args.email) > 254:
            parser.error("A valid beta-user email is required")
        # Exclusive creation avoids overwriting an existing invitation.
        with args.output.open("x", encoding="utf-8") as output:
            output.write(store.invite(args.email) + "\n")
        print("Invitation written to the specified file; expires in 24 hours. No email was sent.")
    else:
        with store.engine.begin() as conn:
            ids = select(users.c.id).where(users.c.email == args.email.lower().strip())
            conn.execute(delete(sessions).where(sessions.c.user_id.in_(ids)))
        print("Sessions revoked")


if __name__ == "__main__":
    main()

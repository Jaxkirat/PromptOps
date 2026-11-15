"""Trusted administrative CLI.

Usage (from the project root, venv activated):

    python -m codeforge.cli create-instructor-invite --email instructor@example.com
    python -m codeforge.cli create-instructor-invite --email instructor@example.com --hours 48
"""

from __future__ import annotations

import argparse
import logging
import sys

from codeforge.config.settings import get_settings
from codeforge.database.database import init_db
from codeforge.exceptions import InvitationError, RegistrationError
from codeforge.services.invitation_service import create_instructor_invitation


def _configure_logging() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def create_invite_command(email: str, hours: int | None) -> int:
    init_db()
    try:
        created = create_instructor_invitation(email, expires_hours=hours)
    except (InvitationError, RegistrationError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print("Instructor invitation created.")
    print(f"  Email:   {created.email}")
    print(f"  Expires: {created.expires_at.isoformat()} ({created.expires_in_hours}h)")
    print(f"  URL:     {created.invite_url}")
    print()
    print("Share this URL once. The token is not stored in plaintext.")
    return 0


def main(argv: list[str] | None = None) -> int:
    _configure_logging()
    parser = argparse.ArgumentParser(prog="codeforge.cli", description="CodeForge admin CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    invite = sub.add_parser(
        "create-instructor-invite",
        help="Generate a single-use instructor invitation URL (trusted, server-side).",
    )
    invite.add_argument("--email", required=True, help="Intended instructor email.")
    invite.add_argument(
        "--hours",
        type=int,
        default=None,
        help="Expiry in hours (default: INVITE_EXPIRY_HOURS from settings).",
    )

    args = parser.parse_args(argv)
    if args.command == "create-instructor-invite":
        return create_invite_command(args.email, args.hours)
    parser.error("Unknown command")
    return 2


if __name__ == "__main__":
    sys.exit(main())

"""Ephemeral local-development credentials for scripts/dev-start.sh.

The startup script owns one credential pair for the whole environment: a random JWT
signing secret and one token minted from that exact secret. Both live only in process
environment variables and disappear when the environment stops, so a token cannot be
replayed against a backend started later.

Secrets are read from the process environment rather than from command-line arguments,
so they are not exposed in the process argument list. Nothing here prints a secret or a
token except ``token``, whose single line of output the startup script captures into an
environment variable.
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.auth.jwt_service import JWTService  # noqa: E402
from app.config.settings import (  # noqa: E402
    JWT_SECRET_KEY_ENV_VAR,
    MINIMUM_JWT_SECRET_LENGTH,
    get_jwt_secret_key,
)
from app.models.jwt_claims import Role  # noqa: E402

# 48 URL-safe bytes comfortably exceeds the minimum the platform accepts.
SECRET_BYTES = 48

DEV_TOKEN_ENV_VAR = "EASP_DEV_API_TOKEN"
DEFAULT_ROLE = Role.ANALYST
DEFAULT_LIFETIME_MINUTES = 24 * 60
DEFAULT_SUBJECT = "local-dev-console"
DEFAULT_AGENT_ID = "agent-1"


def generate_secret() -> str:
    """Return a random signing secret for one development environment."""
    secret = secrets.token_urlsafe(SECRET_BYTES)
    if len(secret.encode("utf-8")) < MINIMUM_JWT_SECRET_LENGTH:  # pragma: no cover
        raise RuntimeError("generated secret is shorter than the platform minimum")
    return secret


def mint_dev_token(
    secret_key: str,
    role: Role = DEFAULT_ROLE,
    lifetime_minutes: int = DEFAULT_LIFETIME_MINUTES,
    subject: str = DEFAULT_SUBJECT,
    agent_id: str = DEFAULT_AGENT_ID,
) -> str:
    """Mint a development token signed with ``secret_key``.

    Uses the platform's own ``JWTService``, so a token minted here is verified by the
    backend exactly like any other token. The backend must run with the same secret.
    """
    service = JWTService(secret_key=secret_key, expiration_minutes=lifetime_minutes)
    return service.create_token(subject=subject, agent_id=agent_id, role=role)


def _request_status(url: str, token: str | None) -> int:
    """Return the HTTP status for ``url``, sending ``token`` when provided."""
    request = urllib.request.Request(url)
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code


def _command_secret(_: argparse.Namespace) -> int:
    print(generate_secret())
    return 0


def _command_token(args: argparse.Namespace) -> int:
    # get_jwt_secret_key applies the same validation the backend applies at startup,
    # so an unusable secret fails here rather than at the first request.
    secret_key = get_jwt_secret_key()
    print(mint_dev_token(secret_key, role=Role(args.role), lifetime_minutes=args.lifetime_minutes))
    return 0


def _command_smoke(args: argparse.Namespace) -> int:
    """Verify the credential pair works and that the boundary still rejects callers."""
    import os

    token = os.environ.get(DEV_TOKEN_ENV_VAR, "")
    if not token:
        print(f"error: {DEV_TOKEN_ENV_VAR} is not set", file=sys.stderr)
        return 2

    url = f"{args.base_url.rstrip('/')}{args.path}"

    authenticated = _request_status(url, token)
    unauthenticated = _request_status(url, None)

    print(f"authenticated {args.path}: {authenticated}")
    print(f"unauthenticated {args.path}: {unauthenticated}")

    if authenticated != 200:
        print(
            "error: the development token was rejected by the backend.\n"
            "The backend must run with the same JWT_SECRET_KEY the token was minted from.\n"
            "Start the environment with scripts/dev-start.sh so one secret and token pair is used.",
            file=sys.stderr,
        )
        return 1

    if unauthenticated != 401:
        print(
            f"error: {args.path} answered {unauthenticated} without credentials; "
            "authentication must stay enforced.",
            file=sys.stderr,
        )
        return 1

    return 0


def _command_summary(args: argparse.Namespace) -> int:
    """Print a redacted description of the environment, never the values themselves."""
    import os

    token = os.environ.get(DEV_TOKEN_ENV_VAR, "")
    secret = os.environ.get(JWT_SECRET_KEY_ENV_VAR, "")
    print(
        json.dumps(
            {
                "role": args.role,
                "token_lifetime_minutes": args.lifetime_minutes,
                "jwt_secret": f"<redacted, {len(secret)} characters>",
                "dev_api_token": f"<redacted, {len(token)} characters>",
            },
            indent=2,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)

    secret_parser = subcommands.add_parser("secret", help="print a new signing secret")
    secret_parser.set_defaults(handler=_command_secret)

    token_parser = subcommands.add_parser(
        "token",
        help=f"print a token signed with ${JWT_SECRET_KEY_ENV_VAR}",
    )
    # ANALYST by default; ADMIN is the explicit opt-in for admin and runtime-execution
    # endpoints. AGENT is a runtime principal and is not a console role.
    token_parser.add_argument(
        "--role",
        default=DEFAULT_ROLE.value,
        choices=[Role.ANALYST.value, Role.ADMIN.value],
    )
    token_parser.add_argument("--lifetime-minutes", type=int, default=DEFAULT_LIFETIME_MINUTES)
    token_parser.set_defaults(handler=_command_token)

    smoke_parser = subcommands.add_parser(
        "smoke",
        help=f"check ${DEV_TOKEN_ENV_VAR} against a protected endpoint",
    )
    smoke_parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    smoke_parser.add_argument("--path", default="/api/v1/agents")
    smoke_parser.set_defaults(handler=_command_smoke)

    summary_parser = subcommands.add_parser("summary", help="print a redacted summary")
    summary_parser.add_argument("--role", default=DEFAULT_ROLE.value)
    summary_parser.add_argument("--lifetime-minutes", type=int, default=DEFAULT_LIFETIME_MINUTES)
    summary_parser.set_defaults(handler=_command_summary)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

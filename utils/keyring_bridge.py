#--------------------#
# keyring_bridge.py
# stores the github token in the os keychain, never in a config file
#--------------------#
from __future__ import annotations

from typing import Optional

import keyring
import keyring.errors

SERVICE = "can_decoder_app"
USERNAME = "github_token"


# raised when the os has no usable keyring backend
class KeyringUnavailableError(RuntimeError):
    pass


# no backend reads as no token instead of crashing
def get_github_token() -> Optional[str]:
    try:
        return keyring.get_password(SERVICE, USERNAME)
    except keyring.errors.KeyringError:
        return None


def set_github_token(token: str) -> None:
    try:
        keyring.set_password(SERVICE, USERNAME, token)
    except keyring.errors.KeyringError as exc:
        raise KeyringUnavailableError(
            "No OS keyring backend is available to store the GitHub token."
        ) from exc


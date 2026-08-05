from collections.abc import Callable
from pathlib import Path
from typing import Any

import requests

from toto_ai.api.rate_limit import (
    DEFAULT_RATE_STATE_PATH,
    RequestDiagnostic,
    TotoBriefRequestCoordinator,
    TotoBriefRequestError,
    UncoordinatedRequestCoordinator,
    sanitize_endpoint,
)

BASE_URL = "https://totobrief.com/api/v1/community"


class TotoBriefClient:
    """Client for the TotoBrief community API."""

    def __init__(
        self,
        base_url: str = BASE_URL,
        session: requests.Session | None = None,
        timeout: int = 30,
        coordinator: (
            TotoBriefRequestCoordinator | UncoordinatedRequestCoordinator | None
        ) = None,
        rate_state_path: str | Path = DEFAULT_RATE_STATE_PATH,
        minimum_interval: float = 2.0,
        max_retries: int = 3,
        rate_state_root: str | Path = ".",
        diagnostic_callback: Callable[[RequestDiagnostic], None] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        supplied_session = session is not None
        self.session = session or requests.Session()
        self.timeout = timeout
        if coordinator is not None:
            self.coordinator = coordinator
        elif supplied_session:
            # Explicitly injected sessions are used by deterministic unit tests
            # and callers that already own their transport policy.
            self.coordinator = UncoordinatedRequestCoordinator()
        else:
            self.coordinator = TotoBriefRequestCoordinator(
                state_path=rate_state_path,
                minimum_interval=minimum_interval,
                max_retries=max_retries,
                allowed_root=rate_state_root,
                diagnostic_callback=diagnostic_callback,
            )
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

    def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        response = self.coordinator.request(
            lambda: self.session.get(
                f"{self.base_url}{path}",
                params=params,
                timeout=self.timeout,
            ),
            endpoint=path,
        )
        try:
            response.raise_for_status()
        except requests.RequestException:
            raise TotoBriefRequestError(
                f"TotoBrief request returned HTTP "
                f"{getattr(response, 'status_code', None)}",
                endpoint=sanitize_endpoint(path),
                attempts=self.coordinator.last_request_attempts,
                status_code=getattr(response, "status_code", None),
            ) from None
        try:
            return response.json()
        except (TypeError, ValueError):
            raise TotoBriefRequestError(
                "TotoBrief returned malformed JSON",
                endpoint=sanitize_endpoint(path),
                attempts=self.coordinator.last_request_attempts,
                status_code=getattr(response, "status_code", None),
            ) from None

    def supported_drawings(self) -> Any:
        return self.get_json("/supported-drawings")

    def drawings(self, name: str = "baltbet-main", page: int = 1) -> Any:
        return self.get_json(f"/{name}/drawings", params={"page": page})

    def drawing_info(self, drawing_id: int) -> Any:
        return self.get_json(f"/drawing-info/{drawing_id}")

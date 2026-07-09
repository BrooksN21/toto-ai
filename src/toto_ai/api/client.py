from typing import Any

import requests

BASE_URL = "https://totobrief.com/api/v1/community"


class TotoBriefClient:
    """Client for the TotoBrief community API."""

    def __init__(
        self,
        base_url: str = BASE_URL,
        session: requests.Session | None = None,
        timeout: int = 30,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.timeout = timeout
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

    def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        response = self.session.get(
            f"{self.base_url}{path}",
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def supported_drawings(self) -> Any:
        return self.get_json("/supported-drawings")

    def drawings(self, name: str = "baltbet-main", page: int = 1) -> Any:
        return self.get_json(f"/{name}/drawings", params={"page": page})

    def drawing_info(self, drawing_id: int) -> Any:
        return self.get_json(f"/drawing-info/{drawing_id}")

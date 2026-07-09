from toto_ai.api.client import BASE_URL, TotoBriefClient


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.raise_for_status_called = False

    def raise_for_status(self):
        self.raise_for_status_called = True

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.headers = {}
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return self.response


def test_supported_drawings_requests_supported_drawings_endpoint():
    response = FakeResponse({"data": ["baltbet-main"]})
    session = FakeSession(response)
    client = TotoBriefClient(session=session)

    assert client.supported_drawings() == {"data": ["baltbet-main"]}
    assert session.calls == [
        {
            "url": f"{BASE_URL}/supported-drawings",
            "params": None,
            "timeout": 30,
        }
    ]
    assert response.raise_for_status_called is True


def test_drawings_requests_named_drawings_with_page():
    response = FakeResponse({"data": [{"id": 42}]})
    session = FakeSession(response)
    client = TotoBriefClient(session=session)

    assert client.drawings(name="custom", page=3) == {"data": [{"id": 42}]}
    assert session.calls == [
        {
            "url": f"{BASE_URL}/custom/drawings",
            "params": {"page": 3},
            "timeout": 30,
        }
    ]


def test_drawing_info_requests_drawing_info_endpoint():
    response = FakeResponse({"data": {"id": 17}})
    session = FakeSession(response)
    client = TotoBriefClient(session=session)

    assert client.drawing_info(17) == {"data": {"id": 17}}
    assert session.calls == [
        {
            "url": f"{BASE_URL}/drawing-info/17",
            "params": None,
            "timeout": 30,
        }
    ]

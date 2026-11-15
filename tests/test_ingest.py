from faers import ingest
from faers.ingest import candidate_urls, quarter_range


def test_quarter_range_crosses_year_boundary():
    assert quarter_range("2014q4", "2015q2") == [(2014, 4), (2015, 1), (2015, 2)]


def test_full_window_has_48_quarters():
    assert len(quarter_range("2014q3", "2026q2")) == 48


def test_candidate_urls_try_both_cases():
    urls = candidate_urls(2025, 4)
    assert urls[0].endswith("faers_ascii_2025q4.zip")
    assert urls[1].endswith("faers_ascii_2025Q4.zip")

class FakeResponse:
    def __init__(self, status_code, body=b""):
        self.status_code = status_code
        self.body = body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise ingest.requests.HTTPError(str(self.status_code))

    def iter_content(self, chunk_size):
        yield self.body


def test_download_resumes_from_partial_file(tmp_path, monkeypatch):
    destination = tmp_path / "file.zip"
    (tmp_path / "file.part").write_bytes(b"0123")
    requested = {}

    def fake_get(url, headers, stream, timeout):
        requested.update(headers)
        return FakeResponse(206, b"456789")

    monkeypatch.setattr(ingest.requests, "get", fake_get)
    assert ingest.download("http://x", destination)
    assert requested == {"Range": "bytes=4-"}
    assert destination.read_bytes() == b"0123456789"


def test_download_returns_false_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(ingest.requests, "get", lambda *a, **k: FakeResponse(404))
    assert not ingest.download("http://x", tmp_path / "file.zip")

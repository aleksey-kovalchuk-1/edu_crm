"""A stand-in for the `clamd` client in tests (mirrors fake_keycloak.py's style): no network socket, no
ClamAV container, deterministic per-test behaviour. Exposes only the interface surface
`app.document_jobs.run_document_scan` actually calls: `ping()` and `instream(fileobj)`.

`run_document_scan` takes an injectable `scanner_factory(settings) -> scanner`; pass e.g.
`scanner_factory=lambda settings: FakeClamd(verdict='FOUND', signature='Eicar-Test-Signature')` to a test
instead of pointing at a real `clamd` container.
"""
import clamd


class FakeClamd:
    """One instance is one canned scan outcome, matching real `clamd.ClamdNetworkSocket.instream` responses:
    `{'stream': ('OK', None)}` for clean content, `{'stream': ('FOUND', signature)}` for a hit. Pass
    `raise_connection_error=True` to simulate the container being unreachable (`clamd.ConnectionError`,
    the same exception type the real client raises)."""

    def __init__(self, verdict='OK', signature=None, *, raise_connection_error=False):
        self.verdict = verdict
        self.signature = signature
        self.raise_connection_error = raise_connection_error
        self.ping_calls = 0
        self.instream_calls = 0

    def ping(self):
        self.ping_calls += 1
        if self.raise_connection_error:
            raise clamd.ConnectionError('fake clamd: connection refused')
        return 'PONG'

    def instream(self, fileobj):
        self.instream_calls += 1
        if self.raise_connection_error:
            raise clamd.ConnectionError('fake clamd: connection refused')
        fileobj.read()  # the real client streams and discards the body from the caller's point of view
        return {'stream': (self.verdict, self.signature)}

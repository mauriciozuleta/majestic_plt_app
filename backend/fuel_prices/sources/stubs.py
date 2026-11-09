"""Stub adapters for possible paid providers: interface only, disabled, terms unverified. Nothing here fetches anything and nothing scrapes."""

from .base import SourceAdapter


class _PaidStub(SourceAdapter):
    automatic = False

    def fetch(self, since=None):
        raise NotImplementedError(f'{self.source_id}: licensed provider not implemented — sign a data licence first')


class PlattsStub(_PaidStub):
    source_id = 'platts_stub'


class ArgusStub(_PaidStub):
    source_id = 'argus_stub'


class AirNavStub(_PaidStub):
    """AirNav posts US FBO prices but no terms or API were found. NOT scraped. Ask AirNav for permission or a feed first."""
    source_id = 'airnav_stub'

"""Minimal LMS/website integration boundary (D-246).

A preliminary internal JSON format and adapter interfaces only. The customer's contracts and samples do not exist yet
(D-233), so nothing here opens a network connection, writes to the database, or feeds workflows, reports or
analytics. Real adapters replace the preliminary ones once the contracts are received and approved.
"""
from .adapters import LmsAdapter, PreliminaryLmsAdapter, PreliminaryWebsiteAdapter, WebsiteAdapter
from .records import SCHEMA_VERSION, InboundRecord

__all__ = [
    'SCHEMA_VERSION', 'InboundRecord', 'LmsAdapter', 'WebsiteAdapter', 'PreliminaryLmsAdapter',
    'PreliminaryWebsiteAdapter',
]

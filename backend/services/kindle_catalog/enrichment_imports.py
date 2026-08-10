"""Kindle enrichment importの後方互換facade。"""

from services.kindle_catalog.autobuy_importer import run_autobuy_import
from services.kindle_catalog.kindle_info_importer import run_kindle_info_import

__all__ = ["run_autobuy_import", "run_kindle_info_import"]

from __future__ import annotations

import logging
from functools import cached_property

from longbridge.openapi import Config, ContentContext, OAuthBuilder, QuoteContext

from app.config import AppSettings

logger = logging.getLogger(__name__)


class LongbridgeAuthError(RuntimeError):
    pass


class LongbridgeSessionFactory:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    @cached_property
    def config(self) -> Config:
        client_id = self.settings.longbridge_client_id
        if not client_id:
            raise LongbridgeAuthError(
                "Missing LONGBRIDGE_CLIENT_ID. Set it in .env or environment variables."
            )
        oauth = OAuthBuilder(client_id, self.settings.oauth_callback_port).build(self._on_open_url)
        return Config.from_oauth(
            oauth,
            enable_print_quote_packages=False,
            log_path=str(self.settings.log_dir),
        )

    def build_quote_context(self) -> QuoteContext:
        return QuoteContext(self.config)

    def build_content_context(self) -> ContentContext:
        return ContentContext(self.config)

    @staticmethod
    def _on_open_url(url: str) -> None:
        logger.warning("Open this URL to authorize Longbridge OAuth: %s", url)
        print(f"Open this URL to authorize Longbridge OAuth: {url}")


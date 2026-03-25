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
        if (
            self.settings.longbridge_app_key
            and self.settings.longbridge_app_secret
            and self.settings.longbridge_access_token
        ):
            logger.info("Using Longbridge API key authentication from local configuration.")
            return Config.from_apikey(
                self.settings.longbridge_app_key,
                self.settings.longbridge_app_secret,
                self.settings.longbridge_access_token,
                enable_print_quote_packages=False,
                log_path=str(self.settings.log_dir),
            )

        client_id = self.settings.longbridge_client_id
        if client_id:
            oauth = OAuthBuilder(client_id, self.settings.oauth_callback_port).build(self._on_open_url)
            return Config.from_oauth(
                oauth,
                enable_print_quote_packages=False,
                log_path=str(self.settings.log_dir),
            )

        raise LongbridgeAuthError(
            "Missing Longbridge credentials. Set LONGBRIDGE_APP_KEY/LONGBRIDGE_APP_SECRET/LONGBRIDGE_ACCESS_TOKEN "
            "or provide LONGBRIDGE_CLIENT_ID for OAuth."
        )

    def build_quote_context(self) -> QuoteContext:
        return QuoteContext(self.config)

    def build_content_context(self) -> ContentContext:
        return ContentContext(self.config)

    @staticmethod
    def _on_open_url(url: str) -> None:
        logger.warning("Open this URL to authorize Longbridge OAuth: %s", url)
        print(f"Open this URL to authorize Longbridge OAuth: {url}")

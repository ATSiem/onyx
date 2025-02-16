import abc
from collections.abc import Iterator
from typing import Any

from pydantic import BaseModel

from onyx.configs.constants import DocumentSource
from onyx.connectors.models import Document
from onyx.connectors.models import SlimDocument
from onyx.indexing.indexing_heartbeat import IndexingHeartbeatInterface

SecondsSinceUnixEpoch = float

GenerateDocumentsOutput = Iterator[list[Document]]
GenerateSlimDocumentOutput = Iterator[list[SlimDocument]]


class BaseConnector(abc.ABC):
    REDIS_KEY_PREFIX = "da_connector_data:"

    @abc.abstractmethod
    def load_credentials(self, credentials: dict[str, Any]) -> dict[str, Any] | None:
        raise NotImplementedError

    @staticmethod
    def parse_metadata(metadata: dict[str, Any]) -> list[str]:
        """Parse the metadata for a document/chunk into a string to pass to Generative AI as additional context"""
        custom_parser_req_msg = (
            "Specific metadata parsing required, connector has not implemented it."
        )
        metadata_lines = []
        for metadata_key, metadata_value in metadata.items():
            if isinstance(metadata_value, str):
                metadata_lines.append(f"{metadata_key}: {metadata_value}")
            elif isinstance(metadata_value, list):
                if not all([isinstance(val, str) for val in metadata_value]):
                    raise RuntimeError(custom_parser_req_msg)
                metadata_lines.append(f'{metadata_key}: {", ".join(metadata_value)}')
            else:
                raise RuntimeError(custom_parser_req_msg)
        return metadata_lines

    @abc.abstractmethod
    def validate_connector_settings(self) -> None:
        """
        Override this if your connector needs to validate credentials or settings.
        Raise an exception if invalid, otherwise do nothing.

        Default is a no-op (always successful).
        """


# Large set update or reindex, generally pulling a complete state or from a savestate file
class LoadConnector(BaseConnector):
    @abc.abstractmethod
    def load_from_state(self) -> GenerateDocumentsOutput:
        raise NotImplementedError


# Small set updates by time
class PollConnector(BaseConnector):
    @abc.abstractmethod
    def poll_source(
        self, start: SecondsSinceUnixEpoch, end: SecondsSinceUnixEpoch
    ) -> GenerateDocumentsOutput:
        raise NotImplementedError


class SlimConnector(BaseConnector):
    @abc.abstractmethod
    def retrieve_all_slim_documents(
        self,
        start: SecondsSinceUnixEpoch | None = None,
        end: SecondsSinceUnixEpoch | None = None,
        callback: IndexingHeartbeatInterface | None = None,
    ) -> GenerateSlimDocumentOutput:
        raise NotImplementedError


class OAuthConnector(BaseConnector):
    class AdditionalOauthKwargs(BaseModel):
        # if overridden, all fields should be str type
        pass

    @classmethod
    @abc.abstractmethod
    def oauth_id(cls) -> DocumentSource:
        raise NotImplementedError

    @classmethod
    @abc.abstractmethod
    def oauth_authorization_url(
        cls,
        base_domain: str,
        state: str,
        additional_kwargs: dict[str, str],
    ) -> str:
        raise NotImplementedError

    @classmethod
    @abc.abstractmethod
    def oauth_code_to_token(
        cls,
        base_domain: str,
        code: str,
        additional_kwargs: dict[str, str],
    ) -> dict[str, Any]:
        raise NotImplementedError


# Event driven
class EventConnector(BaseConnector):
    @abc.abstractmethod
    def handle_event(self, event: Any) -> GenerateDocumentsOutput:
        raise NotImplementedError


class ConnectorValidationError(Exception):
    """General exception for connector validation errors."""


class CredentialExpiredError(ConnectorValidationError):
    """Raised when a connector's credential is expired."""


class InsufficientPermissionsError(ConnectorValidationError):
    """Raised when the credential does not have sufficient API permissions."""

from typing import Any
from typing import cast
from typing import IO
import os

from unstructured.staging.base import dict_to_elements
from unstructured_client import UnstructuredClient  # type: ignore
from unstructured_client.models import operations  # type: ignore
from unstructured_client.models import shared

from onyx.configs.constants import KV_UNSTRUCTURED_API_KEY
from onyx.key_value_store.factory import get_kv_store
from onyx.key_value_store.interface import KvKeyNotFoundError
from onyx.utils.logger import setup_logger


logger = setup_logger()


def get_unstructured_api_key() -> str | None:
    kv_store = get_kv_store()
    try:
        return cast(str, kv_store.load(KV_UNSTRUCTURED_API_KEY))
    except KvKeyNotFoundError:
        return None


def update_unstructured_api_key(api_key: str) -> None:
    kv_store = get_kv_store()
    kv_store.store(KV_UNSTRUCTURED_API_KEY, api_key)


def delete_unstructured_api_key() -> None:
    kv_store = get_kv_store()
    kv_store.delete(KV_UNSTRUCTURED_API_KEY)


def _sdk_partition_request(
    file: IO[Any], file_name: str, **kwargs: Any
) -> operations.PartitionRequest:
    file.seek(0, 0)
    try:
        request = operations.PartitionRequest(
            partition_parameters=shared.PartitionParameters(
                files=shared.Files(content=file.read(), file_name=file_name),
                **kwargs,
            ),
        )
        return request
    except Exception as e:
        logger.error(f"Error creating partition request for file {file_name}: {str(e)}")
        raise


def unstructured_to_text(file: IO[Any], file_name: str) -> str:
    logger.debug(f"Starting to read file: {file_name}")
    req = _sdk_partition_request(file, file_name, strategy="fast")

    local_api_url = os.getenv("UNSTRUCTURED_API_URL")
    api_key = get_unstructured_api_key()

    if local_api_url:
        try:
            logger.debug(f"Using local Unstructured API at {local_api_url}")
            unstructured_client = UnstructuredClient(
                server_url=local_api_url,
                api_key_auth=api_key,
            )
            response = unstructured_client.general.partition(req)  # type: ignore
            
            if not hasattr(response, 'elements'):
                err = f"Invalid response from local Unstructured API: missing elements"
                logger.error(err)
                raise ValueError(err)
                
            elements = dict_to_elements(response.elements)
            return "\n\n".join(str(el) for el in elements)
            
        except Exception as e:
            err = f"Failed to use local Unstructured API (configured at {local_api_url}): {str(e)}"
            logger.error(err)
            raise ValueError(err)
    
    # Only reach here if no local API configured
    logger.debug("No local API configured, using public Unstructured API")
    unstructured_client = UnstructuredClient(api_key_auth=api_key)
    response = unstructured_client.general.partition(req)  # type: ignore
    
    if not hasattr(response, 'elements'):
        err = f"Invalid response from public Unstructured API: missing elements"
        logger.error(err)
        raise ValueError(err)
        
    elements = dict_to_elements(response.elements)
    return "\n\n".join(str(el) for el in elements)

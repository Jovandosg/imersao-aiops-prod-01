import asyncio
import json
import logging

from kubernetes import client, config
from kubernetes.config import ConfigException

logger = logging.getLogger(__name__)


def load_config() -> None:
    try:
        config.load_incluster_config()
        logger.info("Kubernetes: autenticado via in-cluster config")
    except ConfigException:
        config.load_kube_config()
        logger.info("Kubernetes: autenticado via kubeconfig")


class KubernetesEventSource:
    """Lista eventos Warning de todos os namespaces (events.k8s.io/v1) como dicts da API.

    O SDK sincrono roda em thread para nao bloquear o event loop. A resposta e lida
    crua (`_preload_content=False`) porque o model pydantic `EventsV1Event` do SDK 37
    exige `eventTime`, que vem nulo nos eventos legados (kubelet, scheduler) e quebra
    a desserializacao. A configuracao e carregada na primeira listagem; uma falha ali
    e tratada como qualquer outro erro de coleta.
    """

    def __init__(self) -> None:
        self._api: client.EventsV1Api | None = None

    def _list_sync(self) -> list[dict]:
        if self._api is None:
            load_config()
            self._api = client.EventsV1Api()
        response = self._api.list_event_for_all_namespaces(
            field_selector="type=Warning",
            _preload_content=False,
        )
        return json.loads(response.data)["items"]

    async def list(self) -> list[dict]:
        return await asyncio.to_thread(self._list_sync)

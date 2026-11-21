"""Model providers: one completion protocol, local adapter first; cloud adapters come later."""

from kata_worker.providers.base import TASK_CLASSES, Provider, ProviderError
from kata_worker.providers.local import LocalProvider

__all__ = ["TASK_CLASSES", "LocalProvider", "Provider", "ProviderError"]

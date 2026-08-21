from abc import ABC
from abc import abstractmethod


class BaseProvider(ABC):

    @abstractmethod
    def chat_completion(
        self,
        model: str,
        messages: list,
        temperature: float = 0,
        timeout: float = 10.0
    ):
        pass
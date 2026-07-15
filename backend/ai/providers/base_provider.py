from abc import ABC
from abc import abstractmethod


class BaseProvider(ABC):

    @abstractmethod
    def chat_completion(
        self,
        model: str,
        messages: list,
        temperature: float = 0
    ):
        pass
import time

from services.provider_health_service import (
    ProviderHealthService
)

from fastapi import responses
from asyncio import timeouts
from ai.providers.provider_factory import (
    ProviderFactory
)

from services.fallback_service import (
    FallbackService
)

import logging

logger = logging.getLogger(__name__)


class LLMExecutionService:

    @staticmethod
    def execute(
        purpose: str,
        messages: list,
        temperature: float = 0,
        company_id = None
    ):

        models = (
            FallbackService
            .get_models_for_purpose(
                purpose,
                company_id=company_id
            )
        )

        last_error = None

        for model_config in models:

            try:

                provider = (
                    ProviderFactory
                    .get_provider(
                        model_config[
                            "provider_type"
                        ],
                        company_id=company_id,
                        provider_id=model_config.get("provider_id")
                    )
                )

                logger.info(
                    f"Trying "
                    f"{model_config['provider_type']}"
                    f"/"
                    f"{model_config['model_name']}"
                )

                start_time = time.time()

                response = (
                    provider.chat_completion(
                        model=
                            model_config[
                                "model_name"
                            ],

                        messages=
                            messages,

                        temperature=
                            temperature
                    )
                )

                response_ms = (
                    time.time() - start_time
                ) * 1000

                # TEMP_PIPELINE_TRACE_REMOVE_LATER
                try:
                    from semantic.diagnostic_trace import PipelineDiagnosticTracer
                    if purpose == "sql_generation":
                        PipelineDiagnosticTracer.record_timing("ollama", response_ms / 1000.0)
                    elif purpose == "business_summary":
                        PipelineDiagnosticTracer.record_timing("summary_llm", response_ms / 1000.0)
                except Exception:
                    pass

                # Recorded against the provider ROW, not the type. Health kept
                # by type meant one account's rate limit marked every Groq
                # provider failed, which is why the control centre showed a
                # red badge on rows that were answering normally.
                _provider_id = model_config.get("provider_id")
                if _provider_id:
                    ProviderHealthService.mark_success_by_id(
                        str(_provider_id), response_ms
                    )
                else:
                    ProviderHealthService.mark_success(
                        model_config["provider_type"], response_ms
                    )

                return response

            except Exception as ex:
                last_error = ex

                _provider_id = model_config.get("provider_id")
                if _provider_id:
                    ProviderHealthService.mark_failure_by_id(
                        str(_provider_id), str(ex)
                    )
                else:
                    ProviderHealthService.mark_failure(
                        model_config["provider_type"], str(ex)
                    )

                

                logger.exception(
                    "Model execution failed."
                )

        if last_error is None:
            raise ValueError(f"No active LLM models configured/available for purpose: {purpose}")
        raise last_error
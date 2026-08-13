import os
import time
import importlib
from dataclasses import dataclass

from dotenv import load_dotenv
from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam
from transformers import AutoModelForCausalLM, AutoTokenizer

from token_usage import GenerationContext, TokenMeasurement, TokenUsageRecorder


load_dotenv()


LOCAL_MODELS = frozenset({
    'Qwen2.5-Coder-7B-Instruct',
    'deepseek-coder-7b-instruct-v1.5',
})


@dataclass(frozen=True)
class ApiModelConfig:
    api_key_env: str
    base_url_env: str
    default_base_url: str | None = None
    request_model_env: str | None = None


API_MODEL_CONFIGS = {
    'gpt-4o-mini-2024-07-18': ApiModelConfig(
        api_key_env='OPENAI_API_KEY',
        base_url_env='OPENAI_BASE_URL',
    ),
    'gemini-1.5-flash-002': ApiModelConfig(
        api_key_env='GEMINI_API_KEY',
        base_url_env='GEMINI_BASE_URL',
        default_base_url='https://generativelanguage.googleapis.com/v1beta/openai/',
    ),
    'openrouter': ApiModelConfig(
        api_key_env='OPENROUTER_API_KEY',
        base_url_env='OPENROUTER_BASE_URL',
        default_base_url='https://openrouter.ai/api/v1',
        request_model_env='OPENROUTER_MODEL',
    ),
}
API_MODELS = frozenset(API_MODEL_CONFIGS)
SUPPORTED_MODELS = LOCAL_MODELS | API_MODELS
DEFAULT_MODEL = 'deepseek-coder-7b-instruct-v1.5'
DEFAULT_MAX_TOKENS = 1024
GENERATION_TEMPERATURE = 0.8
SAMPLING_ENABLED = True


def load_model(model_name):
    if model_name in LOCAL_MODELS:
        model_name = f"./LLMs/{model_name}"

        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            torch_dtype="auto",
            device_map="auto"
        )
        tokenizer = AutoTokenizer.from_pretrained(model_name)
    else:
        exit()

    return model, tokenizer


def generate_code(
    args,
    prompt,
    model,
    tokenizer,
    max_new_tokens=DEFAULT_MAX_TOKENS,
    usage_recorder: TokenUsageRecorder | None = None,
    context: GenerationContext | None = None,
) -> str:
    if args.debug:
        print(prompt)
    messages = [
        {"role": "user", "content": prompt}
    ]
    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True
    )
    model_inputs = tokenizer([text], return_tensors="pt").to(model.device)

    generated_ids = model.generate(
        **model_inputs,
        max_new_tokens=max_new_tokens,
        pad_token_id=tokenizer.eos_token_id,
        eos_token_id=tokenizer.eos_token_id,
        do_sample=SAMPLING_ENABLED,
        temperature=GENERATION_TEMPERATURE,
    )

    input_tokens = int(model_inputs.input_ids.shape[-1])
    generated_ids = [
        output_ids[len(input_ids):] for input_ids, output_ids in zip(model_inputs.input_ids, generated_ids)
    ]
    output_tokens = sum(len(output_ids) for output_ids in generated_ids)
    _record_usage(
        usage_recorder,
        context,
        TokenMeasurement(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            source="model_tokenizer",
        ),
    )
    code = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]

    if args.debug:
        print(code)

    return code


def generate_text(
    args,
    prompt,
    model,
    tokenizer,
    max_tokens=DEFAULT_MAX_TOKENS,
    usage_recorder: TokenUsageRecorder | None = None,
    context: GenerationContext | None = None,
) -> str:
    if args.model_name in LOCAL_MODELS:
        return generate_code(
            args,
            prompt,
            model,
            tokenizer,
            max_tokens,
            usage_recorder,
            context,
        )
    if args.model_name in API_MODELS:
        return generate_code_api(
            args,
            prompt,
            max_tokens,
            usage_recorder,
            context,
        )
    supported = ", ".join(sorted(SUPPORTED_MODELS))
    raise ValueError(f"Unsupported model '{args.model_name}'. Supported models: {supported}")


def _create_api_client(model_name: str) -> OpenAI:
    config = _get_api_model_config(model_name)

    api_key = os.getenv(config.api_key_env)
    if not api_key:
        raise RuntimeError(
            f"Missing API key: set environment variable {config.api_key_env}"
        )

    base_url = os.getenv(config.base_url_env, config.default_base_url)
    default_headers = _openrouter_headers() if model_name == "openrouter" else None
    if base_url:
        return OpenAI(
            api_key=api_key,
            base_url=base_url,
            default_headers=default_headers,
        )
    return OpenAI(api_key=api_key, default_headers=default_headers)


def resolve_api_model_name(model_name: str) -> str:
    config = _get_api_model_config(model_name)
    if config.request_model_env is None:
        return model_name

    request_model = os.getenv(config.request_model_env)
    if not request_model:
        raise RuntimeError(
            f"Missing API model: set environment variable {config.request_model_env}"
        )
    return request_model


def effective_model_name(model_name: str) -> str:
    if model_name in API_MODELS:
        return resolve_api_model_name(model_name)
    return model_name


def _get_api_model_config(model_name: str) -> ApiModelConfig:
    try:
        return API_MODEL_CONFIGS[model_name]
    except KeyError:
        raise ValueError(f"Unsupported API model '{model_name}'") from None


def _openrouter_headers() -> dict[str, str] | None:
    headers = {}
    http_referer = os.getenv("OPENROUTER_HTTP_REFERER")
    app_title = os.getenv("OPENROUTER_APP_TITLE")
    if http_referer:
        headers["HTTP-Referer"] = http_referer
    if app_title:
        headers["X-OpenRouter-Title"] = app_title
    return headers or None


def generate_code_api(
    args,
    prompt,
    max_tokens=DEFAULT_MAX_TOKENS,
    usage_recorder: TokenUsageRecorder | None = None,
    context: GenerationContext | None = None,
) -> str:
    if args.debug:
        print(prompt)
    client = _create_api_client(args.model_name)
    request_model = resolve_api_model_name(args.model_name)
    messages: list[ChatCompletionMessageParam] = [
        {"role": "user", "content": prompt}
    ]

    retry = 1000
    code = ""
    completion = None
    while retry:
        try:
            retry -= 1
            completion = client.chat.completions.create(model=request_model,
                                                        messages=messages,
                                                        temperature=GENERATION_TEMPERATURE,
                                                        max_tokens=max_tokens)
            code = completion.choices[0].message.content or ""
            break
        except Exception as e:
            time.sleep(60)
            print(e, 'sleep and retry!')
            continue

    if completion is not None:
        _record_usage(
            usage_recorder,
            context,
            _api_token_measurement(completion, prompt, code),
        )

    if args.debug:
        print(code)
    return code


def _api_token_measurement(completion, prompt: str, output: str) -> TokenMeasurement:
    usage = completion.usage
    if usage is not None:
        input_tokens = getattr(usage, "prompt_tokens", None)
        if input_tokens is None:
            input_tokens = getattr(usage, "input_tokens", None)
        output_tokens = getattr(usage, "completion_tokens", None)
        if output_tokens is None:
            output_tokens = getattr(usage, "output_tokens", None)
        if input_tokens is not None and output_tokens is not None:
            return TokenMeasurement(
                input_tokens=int(input_tokens),
                output_tokens=int(output_tokens),
                source="api_usage",
            )

    try:
        tiktoken = importlib.import_module("tiktoken")
        encoding = tiktoken.get_encoding("cl100k_base")
        input_tokens = len(encoding.encode(prompt))
        output_tokens = len(encoding.encode(output))
        source = "tiktoken_estimate"
    except ImportError:
        input_tokens = _estimate_tokens_from_characters(prompt)
        output_tokens = _estimate_tokens_from_characters(output)
        source = "character_estimate"

    return TokenMeasurement(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        source=source,
        estimated=True,
    )


def _estimate_tokens_from_characters(text: str) -> int:
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def _record_usage(
    recorder: TokenUsageRecorder | None,
    context: GenerationContext | None,
    measurement: TokenMeasurement,
) -> None:
    if recorder is None:
        return
    if context is None:
        raise ValueError("GenerationContext is required when token tracking is enabled")
    recorder.record(context, measurement)

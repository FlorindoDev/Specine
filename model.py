import time
from openai import OpenAI
from transformers import AutoModelForCausalLM, AutoTokenizer


def load_model(model_name):
    if model_name in ['Qwen2.5-Coder-7B-Instruct', 'deepseek-coder-7b-instruct-v1.5']:
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


def generate_code(args, prompt, model, tokenizer, max_new_tokens=1024):
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

    if args.model_name == 'Qwen2.5-Coder-1.5B-Instruct':
        generated_ids = model.generate(
            **model_inputs,
            max_new_tokens=max_new_tokens,
            pad_token_id=tokenizer.eos_token_id,
            eos_token_id=tokenizer.eos_token_id,
            temperature=0.8
        )
    else:
        generated_ids = model.generate(
            **model_inputs,
            max_new_tokens=max_new_tokens,
            pad_token_id=tokenizer.eos_token_id,
            eos_token_id=tokenizer.eos_token_id,
            temperature=0.8
        )

    generated_ids = [
        output_ids[len(input_ids):] for input_ids, output_ids in zip(model_inputs.input_ids, generated_ids)
    ]
    code = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]

    if args.debug:
        print(code)

    return code


def generate_code_api(args, prompt, max_tokens=1024):
    if args.debug:
        print(prompt)
    if args.model_name == "gpt-4o-mini-2024-07-18":
        client = OpenAI(
            base_url='Base Url',
            api_key='Your API KEY'
        )
    elif args.model_name == "gemini-1.5-flash-002":
        client = OpenAI(
            base_url='Base Url',
            api_key='Your API KEY'
        )
    messages = [
        {"role": "user", "content": prompt}
    ]

    retry = 1000
    while retry:
        try:
            retry -= 1
            completion = client.chat.completions.create(model=args.model_name,
                                                        messages=messages,
                                                        temperature=0.8,
                                                        max_tokens=max_tokens)
            code = completion.choices[0].message.content
            break
        except Exception as e:
            code = None
            time.sleep(60)
            print(e, 'sleep and retry!')
            continue

    if args.debug:
        print(code)
    return code

import asyncio, os
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv() 

client = AsyncOpenAI(
    # This is the default and can be omitted
    api_key=os.environ['CHAT_GPT_API_KEY'],
)

# openai.api_key = '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'

async def get_chatgpt_response():
    response = await client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "сколько планет в солнечной системе ?"}
        ],
        max_tokens=150
    )
    return response.choices[0].message.content

a = asyncio.run(get_chatgpt_response())
print(a)
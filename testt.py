import json,os
from telethon.sync import TelegramClient
from telethon.tl.functions.messages import GetHistoryRequest

# Конфигурация для подключения к Telegram API
api_id = os.getenv('API_ID')
api_hash =os.getenv('API_HASH')
bot_token = os.getenv('BOT_TOKEN')
chat_id = os.getenv('GROUP_ID')  # ID группы

client = TelegramClient('session_name', api_id, api_hash)

async def get_all_messages_from_group(group_name):
    async with client:
        entity = await client.get_entity(group_name)
        all_messages = []
        offset_id = 0
        limit = 100

        while True:
            history = await client(GetHistoryRequest(
                peer=entity,
                offset_id=offset_id,
                offset_date=None,
                add_offset=0,
                limit=limit,
                max_id=0,
                min_id=0,
                hash=0
            ))

            if not history.messages:
                break

            all_messages.extend(history.messages)
            offset_id = history.messages[-1].id

        return all_messages

def split_by_colon(text):
    """
    Разбивает текст на пары 'вопрос-ответ' по двоеточиям.
    """
    pairs = []
    parts = [p.strip() for p in text.split('\n') if p.strip()]

    for part in parts:
        if ':' in part:
            question, answer = part.split(':', 1)
            pairs.append({
                "question": question.strip() + ":",
                "answer": answer.strip()
            })
        elif pairs:
            # Если это продолжение ответа для предыдущего вопроса
            pairs[-1]['answer'] += f"\n{part}"

    # Удаляем пары, где ответ пустой
    return [pair for pair in pairs if pair['answer']]

def prepare_qa_data(messages):
    """
    Формирует список вопросов и ответов из сообщений.
    """
    qa_pairs = []

    for message in messages:
        if not message.message:
            continue

        text = message.message.strip()
        pairs = split_by_colon(text)
        qa_pairs.extend(pairs)

    return qa_pairs

async def save_qa_to_json(messages, filename="qa_data.json"):
    qa_pairs = prepare_qa_data(messages)
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(qa_pairs, f, ensure_ascii=False, indent=4)

async def main():
    group_name = os.getenv('GROUP_NAME')
    messages = await get_all_messages_from_group(group_name)

    # Форматируем и сохраняем данные как QA-пары
    await save_qa_to_json(messages)

    print("Данные сохранены в qa_data.json")

client.loop.run_until_complete(main())



# upload_video.py
import asyncio
from aiogram import Bot
from config import BOT_TOKEN

async def upload_video():
    bot = Bot(token=BOT_TOKEN)
    try:
        with open("media/IMG_0590.MOV", "rb") as video_file:
            result = await bot.send_video(
                chat_id=1097943646,  # O'z chat ID'ingizni kiriting (masalan, bot egasining chat ID'si)
                video=video_file
            )
            file_id = result.video.file_id
            print(f"Video file_id: {file_id}")
    except Exception as e:
        print(f"Xato yuz berdi: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(upload_video())
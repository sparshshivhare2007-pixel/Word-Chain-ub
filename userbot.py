import asyncio
from telethon import TelegramClient, events
from config import Config
from userbot_manager import UserBotManager
from utils.delays import AntiBanDelay

# Validate config
Config.validate()

# Create Telethon client
client = TelegramClient(
    Config.SESSION_NAME,
    Config.API_ID,
    Config.API_HASH
)

manager = UserBotManager()


# ========================
# CONNECT SESSION
# ========================
@client.on(events.NewMessage(pattern=r"\.connect (\w+)"))
async def connect_handler(event):
    session_name = event.pattern_match.group(1).lower()
    user_id = event.sender_id

    await manager.get_or_create_session(user_id, session_name)
    await event.reply(f"✅ Session '{session_name}' created.")


# ========================
# LIST SESSIONS
# ========================
@client.on(events.NewMessage(pattern=r"\.sessions"))
async def sessions_handler(event):
    user_id = event.sender_id
    sessions = manager.get_user_sessions(user_id)

    if not sessions:
        await event.reply("No active sessions.")
        return

    text = "📋 Active Sessions:\n\n"
    for sess in sessions:
        status = "▶️ Active" if sess.active else "⏸️ Idle"
        text += f"• {sess.session_name} | {status}\n"

    await event.reply(text)


# ========================
# PLAY SESSION
# ========================
@client.on(events.NewMessage(pattern=r"\.play (\w+)"))
async def play_handler(event):
    session_name = event.pattern_match.group(1).lower()
    user_id = event.sender_id
    key = manager.get_session_key(user_id, session_name)

    if key not in manager.sessions:
        await event.reply("Session not found. Use .connect first.")
        return

    session = manager.sessions[key]

    if session.task and not session.task.done():
        session.task.cancel()

    session.task = asyncio.create_task(
        auto_play(event, session)
    )

    await event.reply(f"▶️ Sending 5-letter words...")


# ========================
# STOP SESSION
# ========================
@client.on(events.NewMessage(pattern=r"\.stop (\w+)"))
async def stop_handler(event):
    session_name = event.pattern_match.group(1).lower()
    user_id = event.sender_id

    success = await manager.disconnect_session(user_id, session_name)

    if success:
        await event.reply(f"⏹️ Stopped '{session_name}'.")
    else:
        await event.reply("Session not found.")


# ========================
# AUTO PLAY (SIMPLE MODE)
# ========================
async def auto_play(event, session):
    try:
        session.start_new_game("simple_mode")

        for _ in range(Config.MAX_GUESSES):
            guess = session.solver.get_next_guess(session.game_state)

            # Send only 5-letter word
            await event.reply(guess)

            # Fake update so solver changes next word
            from core.state import LetterState
            fake_states = [LetterState.ABSENT] * 5

            session.game_state.add_guess(
                type("GuessResult", (), {
                    "word": guess,
                    "states": fake_states
                })
            )

            await asyncio.sleep(2)

    except asyncio.CancelledError:
        await event.reply("Game stopped.")
        session.active = False


# ========================
# MAIN
# ========================
async def main():
    await client.start()
    print("Telethon Userbot Running...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())

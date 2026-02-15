import asyncio
from telethon import TelegramClient, events
from config import Config
from userbot_manager import UserBotManager
from core.parser import GameResponseParser
from utils.delays import AntiBanDelay
from utils.logger import logger

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

    session = await manager.get_or_create_session(user_id, session_name)
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
        auto_play(event, session, session_name)
    )

    await event.reply(f"▶️ Auto-playing '{session_name}'...")


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
# AUTO PLAY LOGIC
# ========================
async def auto_play(event, session, session_name):
    try:
        session.start_new_game(f"{session.user_id}_{session_name}")

        for turn in range(1, Config.MAX_GUESSES + 1):
            guess = session.solver.get_next_guess(session.game_state)

            await AntiBanDelay.human_typing(len(guess))
            await event.reply(f"🔤 Turn {turn}: `{guess}`")

            # Demo feedback (replace with real parsing later)
            feedback = simulate_feedback(guess)

            result = GameResponseParser.parse_emoji_grid(
                feedback, guess, turn
            )

            if not result:
                await event.reply("Parse error.")
                break

            session.update_game(result)

            if result.is_win():
                await event.reply(f"🎉 Solved in {turn} turns!")
                session.finish_game(guess)
                return

            await AntiBanDelay.between_actions()

        await event.reply("❌ Failed to solve.")
        session.finish_game()

    except asyncio.CancelledError:
        await event.reply("Game stopped.")
        session.active = False


# ========================
# DEMO FEEDBACK (REMOVE LATER)
# ========================
def simulate_feedback(guess):
    target = "crane"
    states = []

    for i, char in enumerate(guess):
        if char == target[i]:
            states.append("🟩")
        elif char in target:
            states.append("🟨")
        else:
            states.append("⬛")

    return "".join(states)


# ========================
# MAIN
# ========================
async def main():
    await client.start()
    print("Telethon Userbot Running...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())

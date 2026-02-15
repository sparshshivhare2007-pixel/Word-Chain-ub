from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler
from config import Config
from userbot_manager import UserBotManager, UserSession
from utils.logger import logger
from pathlib import Path
from core.state import LetterState
import asyncio
import time

manager = UserBotManager()


async def check_force_join(update: Update) -> bool:
    if not Config.FORCE_JOIN_CHAT:
        return True

    user_id = update.effective_user.id
    try:
        chat_member = await update.get_bot().get_chat_member(
            Config.FORCE_JOIN_CHAT, user_id
        )

        if chat_member.status in ["member", "administrator", "creator"]:
            return True

        await update.message.reply_text(
            f"🔒 Please join {Config.FORCE_JOIN_CHAT} to use this bot",
            reply_markup=InlineKeyboardMarkup(
                [[
                    InlineKeyboardButton(
                        "Join Channel",
                        url=f"https://t.me/{Config.FORCE_JOIN_CHAT.lstrip('@')}"
                    )
                ]]
            ),
        )
        return False

    except Exception as e:
        logger.error(f"Force join check failed: {e}")
        return False


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_force_join(update):
        return

    welcome_text = (
        "🎮 Wordle Bot System\n\n"
        "/connect <name>\n"
        "/disconnect <name>\n"
        "/sessions\n"
        "/play <name>\n"
        "/stop <name>\n"
    )

    photo_path = Path(Config.ASSETS_DIR) / "start.jpg"

    if photo_path.exists():
        await update.message.reply_photo(
            photo=open(photo_path, "rb"),
            caption=welcome_text,
        )
    else:
        await update.message.reply_text(welcome_text)


async def connect_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /connect <session_name>")
        return

    session_name = context.args[0].lower()
    user_id = update.effective_user.id

    if not session_name.isalnum():
        await update.message.reply_text("Session name must be alphanumeric")
        return

    try:
        await manager.get_or_create_session(user_id, session_name)
        await update.message.reply_text(
            f"✅ Session '{session_name}' connected!"
        )
    except Exception as e:
        logger.error(f"Connect failed: {e}")
        await update.message.reply_text("❌ Connection failed")


async def play_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /play <session_name>")
        return

    session_name = context.args[0].lower()
    user_id = update.effective_user.id
    key = manager.get_session_key(user_id, session_name)

    if key not in manager.sessions:
        await update.message.reply_text("Session not found. Use /connect first.")
        return

    session = manager.sessions[key]

    if session.task and not session.task.done():
        session.task.cancel()

    session.task = asyncio.create_task(
        auto_play_game(update, context, session, session_name)
    )

    await update.message.reply_text(f"▶️ Starting auto-play for '{session_name}'")


async def stop_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /stop <session_name>")
        return

    session_name = context.args[0].lower()
    user_id = update.effective_user.id
    key = manager.get_session_key(user_id, session_name)

    if key not in manager.sessions:
        await update.message.reply_text("Session not found")
        return

    session = manager.sessions[key]

    if session.task and not session.task.done():
        session.task.cancel()
        await update.message.reply_text("⏸️ Auto-play stopped")


async def auto_play_game(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    session: UserSession,
    session_name: str,
):
    from core.parser import GameResponseParser
    from utils.delays import AntiBanDelay

    try:
        game_id = f"{session.user_id}_{session_name}_{int(time.time())}"
        session.start_new_game(game_id)

        for turn in range(1, Config.MAX_GUESSES + 1):

            guess = session.solver.get_next_guess(session.game_state)

            await AntiBanDelay.human_typing(len(guess))

            await update.message.reply_text(
                f"🔤 [{session_name}] Turn {turn}: `{guess}`",
                parse_mode="Markdown",
            )

            await AntiBanDelay.between_actions()

            feedback = simulate_feedback(guess)

            result = GameResponseParser.parse_emoji_grid(
                feedback, guess, turn
            )

            if not result:
                await update.message.reply_text("⚠️ Feedback parse failed")
                break

            session.update_game(result)

            progress = "".join(
                "🟩" if s == LetterState.CORRECT
                else "🟨" if s == LetterState.PRESENT
                else "⬛"
                for s in result.states
            )

            await update.message.reply_text(
                f"📊 [{session_name}] {progress} ({guess})"
            )

            if result.is_win():
                await update.message.reply_text(
                    f"🎉 Solved in {turn} turns!"
                )
                return

            await AntiBanDelay.between_actions()

    except asyncio.CancelledError:
        await update.message.reply_text("⏹️ Game paused")
        raise
    except Exception as e:
        logger.error(f"Game error: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")


def simulate_feedback(guess: str) -> str:
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


def register_bot_handlers(application):
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("connect", connect_handler))
    application.add_handler(CommandHandler("play", play_handler))
    application.add_handler(CommandHandler("stop", stop_handler))

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Dict, Optional, List
from config import Config
from core.state import GameState
from core.solver import WordleSolver
from utils.logger import logger
from utils.delays import AntiBanDelay

class UserSession:
    def __init__(self, user_id: int, session_name: str):
        self.user_id = user_id
        self.session_name = session_name
        self.solver = WordleSolver()
        self.game_state: Optional[GameState] = None
        self.active = False
        self.last_activity = time.time()
        self.task: Optional[asyncio.Task] = None
        self.session_file = Path(Config.SESSIONS_DIR) / f"{user_id}_{session_name}.json"
    
    def start_new_game(self, game_id: str):
        self.solver.reset()
        self.game_state = GameState(game_id=game_id)
        self.active = True
        self.last_activity = time.time()
        self._save_session()
    
    def update_game(self, guess_result):
        if not self.game_state:
            return
        self.game_state.add_guess(guess_result)
        self.last_activity = time.time()
        self._save_session()
    
    def finish_game(self, target_word: Optional[str] = None):
        if self.game_state:
            self.game_state.target_word = target_word
        self.active = False
        self._save_session()
    
    def _save_session(self):
        if not self.game_state:
            return
        
        data = {
            "user_id": self.user_id,
            "session_name": self.session_name,
            "active": self.active,
            "last_activity": self.last_activity,
            "game_state": self.game_state.to_dict() if self.game_state else None
        }
        
        with open(self.session_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    @classmethod
    def load_session(cls, user_id: int, session_name: str) -> Optional['UserSession']:
        session_file = Path(Config.SESSIONS_DIR) / f"{user_id}_{session_name}.json"
        if not session_file.exists():
            return None
        
        try:
            with open(session_file) as f:
                data = json.load(f)
            
            session = cls(user_id, session_name)
            session.active = data["active"]
            session.last_activity = data["last_activity"]
            
            if data.get("game_state"):
                session.game_state = GameState.from_dict(data["game_state"])
                session.solver.reset()  # Will be updated as guesses come in
            
            # Clean up stale sessions
            if session.active and (time.time() - session.last_activity) > Config.SESSION_TIMEOUT:
                logger.info(f"Cleaning stale session for {user_id}")
                session_file.unlink(missing_ok=True)
                return None
            
            return session
        except Exception as e:
            logger.error(f"Failed to load session {session_file}: {e}")
            return None

class UserBotManager:
    def __init__(self):
        self.sessions: Dict[str, UserSession] = {}  # key: f"{user_id}_{session_name}"
        self._load_persisted_sessions()
    
    def _load_persisted_sessions(self):
        session_files = Path(Config.SESSIONS_DIR).glob("*.json")
        for file in session_files:
            try:
                with open(file) as f:
                    data = json.load(f)
                user_id = data["user_id"]
                session_name = data["session_name"]
                key = f"{user_id}_{session_name}"
                self.sessions[key] = UserSession.load_session(user_id, session_name)
                logger.info(f"Loaded session: {key}")
            except Exception as e:
                logger.warning(f"Failed to load {file}: {e}")
    
    def get_session_key(self, user_id: int, session_name: str) -> str:
        return f"{user_id}_{session_name}"
    
    async def create_session(self, user_id: int, session_name: str) -> UserSession:
        key = self.get_session_key(user_id, session_name)
        
        # Clean up old sessions if over limit
        user_sessions = [k for k in self.sessions if k.startswith(f"{user_id}_")]
        if len(user_sessions) >= Config.MAX_SESSIONS_PER_USER:
            oldest = min(user_sessions, key=lambda k: self.sessions[k].last_activity)
            await self.disconnect_session(oldest.split('_')[0], oldest.split('_')[1])
            logger.info(f"Removed oldest session for user {user_id} to respect limit")
        
        session = UserSession(user_id, session_name)
        self.sessions[key] = session
        return session
    
    async def get_or_create_session(self, user_id: int, session_name: str) -> UserSession:
        key = self.get_session_key(user_id, session_name)
        if key not in self.sessions or not self.sessions[key].active:
            return await self.create_session(user_id, session_name)
        return self.sessions[key]
    
    async def disconnect_session(self, user_id: int, session_name: str) -> bool:
        key = self.get_session_key(user_id, session_name)
        if key not in self.sessions:
            return False
        
        session = self.sessions[key]
        if session.task and not session.task.done():
            session.task.cancel()
            try:
                await session.task
            except asyncio.CancelledError:
                pass
        
        session.active = False
        session._save_session()
        del self.sessions[key]
        
        # Cleanup session file
        session.session_file.unlink(missing_ok=True)
        logger.info(f"Disconnected session: {key}")
        return True
    
    def get_user_sessions(self, user_id: int) -> List[UserSession]:
        return [
            sess for key, sess in self.sessions.items()
            if key.startswith(f"{user_id}_")
        ]
    
    async def cleanup_stale_sessions(self):
        """Background task to clean inactive sessions"""
        while True:
            now = time.time()
            stale_keys = [
                key for key, sess in self.sessions.items()
                if not sess.active and (now - sess.last_activity) > Config.SESSION_TIMEOUT
            ]
            
            for key in stale_keys:
                del self.sessions[key]
                logger.debug(f"Cleaned stale session: {key}")
            
            await asyncio.sleep(300)  # Check every 5 minutes

import sqlalchemy as sqla
from sqlalchemy import Column, String, Integer, ForeignKey, DateTime, Numeric
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

import discord

import logging
from typing import Tuple
import datetime

from src import config

logger = logging.getLogger('db')
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename=config.settings['db_log_path'], encoding='utf-8', mode='a')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    discord_id = Column(Numeric, unique=True)
    name = Column(String, unique=True)
    messages = relationship("UserMessage", backref="users")
    message_chains = relationship("AdventureMessageChain", backref="users")


class UserMessage(Base):
    __tablename__ = "user_messages"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    content = Column(String)
    rate_limit_count = Column(Integer, default=0)
    adventure_valid_messages = relationship("AdventureValidMessage", backref="user_messages")
    adventure_invalid_messages = relationship("AdventureInvalidMessage", backref="user_messages")


class AdventureMessageChain(Base):
    __tablename__ = "adventure_chains"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    system = Column(String)
    adventure_seed = Column(String)
    adventure_seed_response = Column(String)
    started_at = Column(DateTime, default=datetime.datetime.utcnow)
    finished_at = Column(DateTime, default=None)
    adventure_valid_message = relationship("AdventureValidMessage", backref="adventure_chains")
    adventure_invalid_message = relationship("AdventureInvalidMessage", backref="adventure_chains")


class AIMessage(Base):
    __tablename__ = "ai_messages"
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    content = Column(String)
    adventure_valid_message = relationship("AdventureValidMessage", backref="ai_messages")
    adventure_invalid_message = relationship("AdventureInvalidMessage", backref="ai_messages")


class AdventureValidMessage(Base):
    __tablename__ = "adventure_valid_message"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_message_id = Column(Integer, ForeignKey('user_messages.id'), nullable=False)
    ai_message_id = Column(Integer, ForeignKey('ai_messages.id'), nullable=False)
    chain_id = Column(Integer, ForeignKey('adventure_chains.id'), nullable=False)


class AdventureInvalidMessage(Base):
    __tablename__ = "adventure_invalid_message"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_message_id = Column(Integer, ForeignKey('user_messages.id'), nullable=False)
    ai_message_id = Column(Integer, ForeignKey('ai_messages.id'), nullable=False)
    chain_id = Column(Integer, ForeignKey('adventure_chains.id'), nullable=False)


class OpenAIAPILog(Base):
    __tablename__ = "openai_api_errors"
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    input_json = Column(String)
    output_json = Column(String)


engine = sqla.create_engine(f"{config.settings['db_path']}")
SessionMaker = sessionmaker(bind=engine)
Base.metadata.create_all(engine)


class AdventureDB:
    def __init__(self):
        self.session = SessionMaker()

    def commit(self):
        self.session.commit()

    def rollback(self):
        self.session.rollback()

    def close(self):
        self.session.rollback()

    def get_discord_user(self, user: discord.User) -> User:
        discord_user = self.session.query(User).filter(User.discord_id == user.id).first()

        return discord_user

    def store_user_message(self, user_id: int, content: str) -> UserMessage:
        discord_user = User(
            id=user_id
        )
        user_message = UserMessage(
            user_id=discord_user.id,
            content=content,
            timestamp=datetime.datetime.utcnow()
        )
        self.session.add(user_message)
        self.session.flush()
        self.session.commit()

        return user_message

    def store_ai_message(self, content: str) -> AIMessage:
        ai_message = AIMessage(
            content=content,
            timestamp=datetime.datetime.utcnow()
        )
        self.session.add(ai_message)
        self.session.flush()

        return ai_message

    def store_valid_message(
            self,
            adventure_chain: AdventureMessageChain,
            user_msg: UserMessage,
            ai_msg: AIMessage
    ) -> AdventureValidMessage:
        valid_message = AdventureValidMessage(
            user_message_id=user_msg.id,
            ai_message_id=ai_msg.id,
            chain_id=adventure_chain.id,
        )
        self.session.add(valid_message)
        self.session.flush()

        return valid_message

    def store_invalid_message(
            self,
            adventure_chain: AdventureMessageChain,
            user_msg: UserMessage,
            ai_msg: AIMessage
    ) -> AdventureInvalidMessage:

        invalid_message = AdventureInvalidMessage(
            user_message_id=user_msg.id,
            ai_message_id=ai_msg.id,
            chain_id=adventure_chain.id,
        )
        self.session.add(invalid_message)
        self.session.flush()

        return invalid_message

    def add_discord_user(self, user: discord.User) -> User:
        discord_user = User(
            discord_id=user.id,
            name=user.name
        )
        self.session.add(discord_user)
        self.session.flush()

        return discord_user

    def get_count_and_recent_msg_timestamp(self, user_id: int) -> Tuple[int, datetime]:
        result = self.session.query(
            sqla.func.sum(UserMessage.rate_limit_count).label("rate_limit_count"),
            sqla.func.min(UserMessage.timestamp).label("oldest_message_timestamp")
        ).filter(
            UserMessage.timestamp < datetime.datetime.utcnow(),
            UserMessage.timestamp >= (datetime.datetime.utcnow() - datetime.timedelta(hours=1)),
            UserMessage.user_id == user_id
        ).one()

        return result.rate_limit_count, result.oldest_message_timestamp

    def create_adventure_chain(
            self,
            user_id: int,
            adventure_system: str,
            adventure_seed: str,
            adventure_seed_response: str) -> AdventureMessageChain:

        adventure_chain = AdventureMessageChain(
            user_id=user_id,
            system=adventure_system,
            adventure_seed=adventure_seed,
            adventure_seed_response=adventure_seed_response
        )
        self.session.add(adventure_chain)
        self.session.flush()

        return adventure_chain

    def get_current_adventure_chain(self, user_id: int) -> AdventureMessageChain:
        current_chain = self.session.query(
            AdventureMessageChain
        ).filter(
            AdventureMessageChain.user_id == user_id
        ).order_by(
            AdventureMessageChain.started_at.desc()
        ).limit(1).first()

        return current_chain

    def get_message_chain(self, current_adventure_chain: AdventureMessageChain):
        message_chain = self.session.query(
            AdventureValidMessage,
            UserMessage,
            AIMessage
        ).join(
            UserMessage,
            (AdventureValidMessage.user_message_id == UserMessage.id)
        ).join(
            AIMessage,
            (AdventureValidMessage.ai_message_id == AIMessage.id)
        ).filter(
            AdventureValidMessage.chain_id == current_adventure_chain.id
        ).with_entities(
            UserMessage.content.label('user'),
            AIMessage.content.label('assistant'),
        ).order_by(
            UserMessage.timestamp.asc()
        )

        messages = [{
            "role": "system",
            "content": f"{current_adventure_chain.system}"
        }, {
            "role": "user",
            "content": f"{current_adventure_chain.adventure_seed}"
        }, {
            "role": "assistant",
            "content": f"{current_adventure_chain.adventure_seed_response}"
        }]
        for r in message_chain.all():
            messages.extend([{
                "role": "user",
                "content": f"{r.user}"
            }, {
                "role": "assistant",
                "content": f"{r.assistant}"
            }])

        return messages

    def store_openai_log(
            self,
            input_str: str,
            output_str: str
    ) -> OpenAIAPILog:
        openai_log = OpenAIAPILog(
            input_json=input_str,
            output_json=output_str,
        )
        self.session.add(openai_log)
        self.session.flush()

        return openai_log

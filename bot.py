import datetime
import logging
import discord
import functools
import asyncio

from src import config
from src.db import AdventureDB, User, UserMessage
from src import openai


logger = logging.getLogger('bot')
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename=config.settings['discord_log_path'], encoding='utf-8', mode='a')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)


intents = discord.Intents.default()
client = discord.Client(intents=intents)


def print_commands(user: User, message: UserMessage, db: AdventureDB) -> str:
    message = ["\n{} {}".format(k, bot_commands[k]['desc']) for k in bot_commands.keys()]
    return " ".join(message)


def repeat_last_message(user: User, message: UserMessage, db: AdventureDB) -> str:
    current_adventure_chain = db.get_current_adventure_chain(user_id=user.id)

    if current_adventure_chain is None:
        response_message = "You are currently not on an adventure. Use !start to begin one or !help for more options."
    else:
        message_chain = db.get_message_chain(current_adventure_chain=current_adventure_chain)
        print(message_chain)
        response_message = message_chain[-1]['content']

    return response_message


def rate_limit_response(user: User, db: AdventureDB):
    # check rate limit
    message_count, oldest_message_timestamp = db.get_count_and_recent_msg_timestamp(user_id=user.id)

    if message_count >= config.settings['hour_message_limit']:  # rate limit exceeded
        reset_time = (oldest_message_timestamp + datetime.timedelta(hours=1)) - datetime.datetime.utcnow()
        return message_count, f"You've reached your limit of {config.settings['hour_message_limit']} " \
                              f"messages per hour." \
                              f" Try again in {round(reset_time.total_seconds() / 60)} minutes."
    else:
        return message_count, None


def start_adventure(user: User, message: UserMessage, db: AdventureDB):
    message_count, response_message = rate_limit_response(user=user, db=db)
    if response_message:
        return response_message

    current_adventure_chain = db.get_current_adventure_chain(user_id=user.id)

    if current_adventure_chain is not None:
        return "You are currently on an adventure. Use !repeat to see the last message."

    adventure_system, adventure_seed, adventure_seed_response = openai.start_adventure_chain(db=db)
    if adventure_seed_response:
        current_adventure_chain = db.create_adventure_chain(
            user_id=user.id,
            adventure_system=adventure_system,
            adventure_seed=adventure_seed,
            adventure_seed_response=adventure_seed_response
        )
        message.rate_limit_count = 1  # openai api call rate limit
        db.commit()
        return f"{adventure_seed_response} ({message_count + 1}/{config.settings['hour_message_limit']})"
    else:
        return "Oops, I'm a bit busy right now. I should be ready in a minute or so..."


bot_commands = {
    "!repeat": {"func": repeat_last_message, "desc": "last adventure message."},
    "!start": {"func": start_adventure, "desc": "a new adventure."},
    # "!end": {"func": repeat_last_message, "desc": "your current adventure."},
    "!help": {"func": print_commands, "desc": "to view commands."},
}


def handle_commands(user: User, message: UserMessage, db: AdventureDB):
    if message.content.lower() in bot_commands:
        response_message = bot_commands[message.content.lower()]["func"](user=user, message=message, db=db)
    else:
        response_message = f"{message.content} is not a valid command. Type !help for valid commands."

    return response_message


async def handle_adventure_message(user: User, message: UserMessage, db: AdventureDB):
    current_adventure_chain = db.get_current_adventure_chain(user_id=user.id)
    if current_adventure_chain is None:  # if there is no existing adventure chain
        response_message = "You are currently not on an adventure. Use !start to begin one or !help for more options."
    else:  # there is an existing adventure chain
        message_count, response_message = rate_limit_response(user=user, db=db)
        print(f"RESP {response_message}")
        if not response_message:
            message_chain = db.get_message_chain(current_adventure_chain=current_adventure_chain)
            # TODO fix this hack
            if len(message_chain) > 21:
                print(f"len(message_chain)={len(message_chain)}")
                # print(message_chain)
                message_chain = [message_chain[0]] + message_chain[-21:]
            message.rate_limit_count = 1  # openai api call rate limit
            db.commit()
            ai_response = openai.generate_invalid_message(
                message=message.content,
                message_chain=message_chain,
                db=db
            )
            if ai_response:  # if there is an invalid response
                ai_response_message = db.store_ai_message(content=ai_response)
                db.store_invalid_message(
                    adventure_chain=current_adventure_chain,
                    ai_msg=ai_response_message,
                    user_msg=message
                )
            else:  # response is valid so generate next step
                ai_response = openai.generate_adventure_ai_response(
                    message=message.content,
                    message_chain=message_chain,
                    db=db
                )
                ai_response_message = db.store_ai_message(content=ai_response)
                db.store_valid_message(
                    adventure_chain=current_adventure_chain,
                    ai_msg=ai_response_message,
                    user_msg=message
                )
            response_message = f"<@{user.discord_id}> {ai_response_message.content} " \
                               f"({message_count+1}/{config.settings['hour_message_limit']})"

    return response_message


@client.event
async def on_ready():
    print('We have logged in as {0.user}'.format(client))


@client.event
async def on_message(message):
    try:
        print(f"content={message.content}")
        # if this is the bot
        if message.author == client.user:
            return

        if message.content:
            db = AdventureDB()
            user = db.get_discord_user(user=message.author)
            if user is None:
                user = db.add_discord_user(user=message.author)
            logger.debug(f"user={user.name}#{user.id} message.content={message.content}")
            clean_message = message.content[message.content.find('>')+2:]   # remove <@> from message
            user_message = db.store_user_message(user_id=user.id, content=clean_message)  # store message

            if clean_message.find("!") == 0:
                response_message = handle_commands(user=user, message=user_message, db=db)
            else:
                response_message = await client.loop.run_in_executor(None, run_coroutine, handle_adventure_message(user, user_message, db))
                # response_message = await handle_adventure_message(user=user, message=user_message, db=db)

            db.commit()
            db.close()

            await message.channel.send(response_message)
    except Exception as e:
        logger.exception(e)
        raise e


def run_coroutine(coro):
    return asyncio.run(coro)


client.run(config.settings['discord_bot_token'])
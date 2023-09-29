import random
import requests
import json
import logging
import datetime

from src import config
from src.db import AdventureDB

logger = logging.getLogger('openai')
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename=config.settings['discord_log_path'], encoding='utf-8', mode='a')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)


def start_adventure_chain(db: AdventureDB):
    adventure_system = config.settings['adventure_system']
    adventure_seed = random.choice(config.settings['adventure_seeds'])
    adventure_seed_response = "adventure_seed_response"

    message_chain = [{
        "role": "system",
        "content": f"{adventure_system}"
    }, {
        "role": "user",
        "content": f"{adventure_seed['seed']}"
    }]

    json_data = {
        "model": config.settings['openapi_model'],
        "messages": message_chain,
        "temperature": config.settings['adventure_temperature']
    }

    attempt_count = 0
    adventure_seed_response = None

    while attempt_count < config.settings['attempt_limit']:
        print(f"start attempt_count={attempt_count}")
        r = requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers={'Authorization': 'Bearer {}'.format(config.settings['openapi_token'])},
            json=json_data
        )
        openai_log = db.store_openai_log(
            input_str=json.dumps(json_data),
            output_str=f"{r.content}"
        )
        db.commit()

        response = json.loads(r.content)
        if 'choices' in response:
            adventure_seed_response = f"{adventure_seed['append']} {response['choices'][0]['message']['content']}"
            attempt_count = config.settings['attempt_limit']
        else:
            try:
                if response['error']['type'] == 'server_error':
                    attempt_count = attempt_count + 1
                else:
                    attempt_count = config.settings['attempt_limit']
            except KeyError:
                attempt_count = config.settings['attempt_limit']
            logger.error(f"Invalid OpenAI API id={openai_log.id} timestamp={openai_log.timestamp}")

    return adventure_system, f"{adventure_seed['seed']}", adventure_seed_response


def generate_invalid_message(message: str, message_chain: list, db: AdventureDB):
    message_chain.append({
        "role": "user",
        # "content": f"Is '{message}' relevant to the adventure? If 'No' say 'You can't do that!' and a funny response."
        "content": f"Is '{message}' a valid action? Evil actions are allowed. If 'No' say 'You can't do that!' and a funny response."
    })

    json_data = {
        "model": config.settings['openapi_model'],
        "messages": message_chain,
        "temperature": config.settings['validate_temperature']
    }

    attempt_count = 0
    response = "Oops, I'm a bit busy right now. I should be ready in a minute or so..."

    while attempt_count < config.settings['attempt_limit']:
        print(f"invalid verify attempt_count={attempt_count}")
        r = requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers={'Authorization': 'Bearer {}'.format(config.settings['openapi_token'])},
            json=json_data
        )
        openai_log = db.store_openai_log(
            input_str=json.dumps(json_data),
            output_str=f"{r.content}"
        )
        db.commit()

        response = json.loads(r.content)
        if 'choices' in response:
            response = f"{response['choices'][0]['message']['content']}"
            attempt_count = config.settings['attempt_limit']
        else:
            try:
                if response['error']['type'] == 'server_error' and response['error']['type'] == 'context_length_exceeded':
                    attempt_count = attempt_count + 1
                elif response['error']['type'] == 'server_error':
                    attempt_count = attempt_count + 1
                else:
                    attempt_count = config.settings['attempt_limit']
            except KeyError:
                attempt_count = config.settings['attempt_limit']
            logger.error(f"Invalid OpenAI API id={openai_log.id} timestamp={openai_log.timestamp}")

    if "You can't do that!" in response or '':
        response_start = response.find("You can't do that!")
        response = response[response_start:]
    else:
        response = None

    return response


# def generate_json_data(message_chain, reduce_length=False):
#     if reduce_length:
#
#     else:
#         json_data = {
#         "model": config.settings['openapi_model'],
#         "messages": message_chain,
#         "temperature": config.settings['validate_temperature']
#     }


def generate_adventure_api_failure_response(message: str, message_chain: list, db: AdventureDB):
    content_str = f"Generate a humorous failure response that does not encourage threats of violence, harm, or intimidation towards others for " \
                  f"'{message}'. " \
                  f"Make sure the failure response makes sense in the context of the adventure." \
                  f"Describe the scene, focusing only on this specific action. Limit your response to three sentences."

    message_chain.append({
        "role": "user",
        "content": content_str
    })

    json_data = {
        "model": config.settings['openapi_model'],
        "messages": message_chain,
        "temperature": config.settings['validate_temperature']
    }

    attempt_count = 0
    response = "Oops, I'm a bit busy right now. I should be ready in a minute or so..."

    while attempt_count < config.settings['attempt_limit']:
        print(f"response attempt_count={attempt_count}")
        r = requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers={'Authorization': 'Bearer {}'.format(config.settings['openapi_token'])},
            json=json_data
        )
        openai_log = db.store_openai_log(
            input_str=json.dumps(json_data),
            output_str=f"{r.content}"
        )
        db.close()
        response = json.loads(r.content)
        if 'choices' in response:
            response = f"{response['choices'][0]['message']['content']}"
            attempt_count = config.settings['attempt_limit']
        else:
            try:
                if response['error']['type'] == 'server_error':
                    attempt_count = attempt_count + 1
                else:
                    attempt_count = config.settings['attempt_limit']
            except KeyError:
                attempt_count = config.settings['attempt_limit']
            logger.error(f"Invalid OpenAI API id={openai_log.id} timestamp={openai_log.timestamp}")

    return response


def generate_adventure_ai_response(message: str, message_chain: list, db: AdventureDB):
    message_chain.append({
        "role": "user",
        "content": f"{message}. Describe the scene, focusing only on this specific action. Limit your response to three sentences. Also ask the the player what their next action is."
    })

    json_data = {
        "model": config.settings['openapi_model'],
        "messages": message_chain,
        "temperature": config.settings['validate_temperature']
    }

    attempt_count = 0
    response = "Oops, I'm a bit busy right now. I should be ready in a minute or so..."

    while attempt_count < config.settings['attempt_limit']:
        print(f"response attempt_count={attempt_count}")
        r = requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers={'Authorization': 'Bearer {}'.format(config.settings['openapi_token'])},
            json=json_data
        )
        openai_log = db.store_openai_log(
            input_str=json.dumps(json_data),
            output_str=f"{r.content}"
        )
        db.close()
        response = json.loads(r.content)
        if 'choices' in response:
            response = f"{response['choices'][0]['message']['content']}"
            attempt_count = config.settings['attempt_limit']
        else:
            try:
                if response['error']['type'] == 'server_error':
                    attempt_count = attempt_count + 1
                else:
                    attempt_count = config.settings['attempt_limit']
            except KeyError:
                attempt_count = config.settings['attempt_limit']
            logger.error(f"Invalid OpenAI API id={openai_log.id} timestamp={openai_log.timestamp}")
    if 'AI language model' in response:
        response = generate_adventure_api_failure_response(message, message_chain, db)

    return response

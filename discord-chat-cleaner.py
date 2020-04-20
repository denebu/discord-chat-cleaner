import click
from datetime import datetime, timezone
import logging
import random
import requests
import string
import time
from tqdm import tqdm
from typing import Generator, Tuple


class DiscordApiError(Exception):
    def __init__(self, *, http_code: int, details: str) -> None:
        message = ''
        if http_code > 0:
            message += f'[HTTP code: {http_code}] '
        message += details
        super().__init__(message)


class Crawler:
    API_URL = 'https://discordapp.com/api/v6'
    HTTP_CODE_MESSAGES = {
        400: "The request was improperly formatted, or the server couldn't understand it.",
        401: "The Authorization header was missing or invalid.",
        403: "The Authorization token you passed did not have permission to the resource.",
        404: "The resource at the location specified doesn't exist.",
        405: "The HTTP method used is not valid for the location specified.",
        502: "There was not a gateway available to process your request. Wait a bit and retry.",
        '5xx': "The server had an error processing your request.",
    }
    RATE_LIMITED_RETRY = 5

    def __init__(self, token: str, default_sleep: float):
        self.s = requests.Session()
        self.s.headers.update({
            'Authorization': token,
            'Content-Type': 'application/json',
        })
        self.default_sleep = default_sleep

    def _request(self, method: str, path: str, params: dict = {}, data=None) -> requests.Response:
        time.sleep(self.default_sleep)
        for i in range(self.RATE_LIMITED_RETRY):
            res = self.s.request(method, f'{self.API_URL}{path}', params, data)
            if res.status_code in self.HTTP_CODE_MESSAGES:
                raise DiscordApiError(http_code=res.status_code, details='\n'.join([
                    self.HTTP_CODE_MESSAGES[res.status_code],
                    res.text,
                ]))
            elif 500 <= res.status_code < 600:  # server error
                raise DiscordApiError(http_code=res.status_code, details=self.HTTP_CODE_MESSAGES['5xx'])
            elif res.status_code == 429:  # rate limits
                retry_after = res.json()['retry_after']
                logging.warning(f'Rate limited. We will sleep {retry_after} ms, and retry it.')
                time.sleep(retry_after / 1000)
                continue
            return res

        logging.critical(f'Failed to request it, although we tried at {self.RATE_LIMITED_RETRY} times.')

    def search_messages_by_author_id(self, room_id: int, room_type: str, author_id: int,
                                     oldest_message_id: int, newest_message_id: int) \
            -> Generator[Tuple[int, list], None, None]:
        offset = 0
        total_results_size = 0

        if room_type.lower() in ['channel', 'guild']:
            room_type = room_type.lower() + 's'
        else:
            raise AssertionError('Invalid room_type argument. room_type should be either "channel" or "guild".')

        while True:
            res = self._request('get', f'/{room_type}/{room_id}/messages/search', {
                'author_id': author_id,
                'include_nsfw': True,
                'offset': offset,
                'sort_by': 'timestamp',
            })
            messages = res.json()
            total_results, messages = messages['total_results'], messages['messages']
            messages = list(map(lambda message_block: list(filter(lambda message: 'hit' in message and message['hit'],
                                                                  message_block))[0], messages))
            unfiltered_results_size = len(messages)
            if unfiltered_results_size == 0 or int(messages[0]['id']) < oldest_message_id:
                break

            messages = list(filter(lambda message: oldest_message_id <= int(message['id']) <= newest_message_id,
                                   messages))
            filtered_results_size = len(messages)
            if filtered_results_size == 0:
                offset += unfiltered_results_size
                continue

            total_results_size += filtered_results_size
            yield total_results_size, messages
            newest_message_id = int(messages[-1]['id']) - 1

    def modify_channel_message_by_message_id(self, channel_id: int, message_id: int, replace_to: str) -> bool:
        try:
            res = self._request('patch', f'/channels/{channel_id}/messages/{message_id}',
                                data=f'{{"content": "{replace_to}"}}')
            return True
        except DiscordApiError as e:
            logging.warning('')
            logging.warning(str(e))
            logging.warning('Skip this message which cannot be done to modify.')
            return False

    def delete_channel_message_by_message_id(self, channel_id: int, message_id: int) -> bool:
        try:
            res = self._request('delete', f'/channels/{channel_id}/messages/{message_id}')
            return True
        except DiscordApiError as e:
            logging.warning('')
            logging.warning(str(e))
            logging.warning('Skip this message which cannot be done to delete.')
            return False


def datetime_to_str(t: datetime = datetime.now(timezone.utc)) -> str:
    return datetime.strftime(t, '%Y-%m-%d %H:%M:%S.%f %z')


def str_to_datetime(s: str) -> datetime:
    return datetime.strptime(s, '%Y-%m-%d %H:%M:%S.%f %z')


def generate_random(min_length=5, max_length=30, chars=''.join([string.digits, string.ascii_letters, '        .,!'])):
    return ''.join(random.choice(chars) for _ in range(random.randrange(min_length, max_length + 1)))


@click.command()
@click.option('--token', type=str, required=True, prompt=True, hide_input=True,
              help='A Discord bot/user token')
@click.option('--token-type', type=click.Choice(['Bot', 'Bearer', 'User'], case_sensitive=False), default='User',
              help='A type of Discord token')
@click.option('--room-id', type=int, required=True,
              help='The room ID to bulky delete (for searching existed messages)')
@click.option('--room-type', type=click.Choice(['channel', 'guild']), required=True,
              help='A type of the room')
@click.option('--author-id', type=int, required=True,
              help='An author ID to bulky delete')
@click.option('--newest-message-id', type=int, required=True,
              help='A newest message ID to bulky delete (We do not check its validity.)')
@click.option('--oldest-message-id', type=int, required=True,
              help='A oldest message ID to bulky delete (We do not check its validity.)')
@click.option('--replace-before-delete', type=click.Choice(['random', 'fixed', 'none'], case_sensitive=False),
              default='None',
              help='Do replace before delete messages?')
@click.option('--replace-to', type=str,
              help='If --replace-before-delete is "Fixed", what message do you replace it to?')
@click.option('--default-sleep', type=click.FloatRange(min=0), default=0,
              help='Default sleep interval per request (sec)')
def main(token, token_type, room_id, room_type, author_id, newest_message_id, oldest_message_id,
         replace_before_delete, replace_to, default_sleep):
    logging.basicConfig(format='%(asctime)s %(levelname)-8s %(funcName)s:%(lineno)d - %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S', level=logging.INFO)
    token_str = f'{token_type} {token}' if token_type != 'User' else token

    logging.info('Started!')

    try:
        crawler = Crawler(token_str, default_sleep)
        generator = crawler.search_messages_by_author_id(room_id, room_type, author_id,
                                                         oldest_message_id, newest_message_id)

        newest_message_id = 0
        total_results_size = 0
        failed_count = 0

        pbar = tqdm(generator)
        for total_results_size, messages in pbar:
            for message in messages:
                if newest_message_id == 0:
                    newest_message_id = int(message['id'])
                    newest_message_datetime = message['timestamp']

                message_id = int(message['id'])
                channel_id = int(message['channel_id'])
                is_success = True
                if replace_before_delete != 'none':
                    if replace_before_delete == 'random':
                        replace_to = generate_random()
                    is_success = crawler.modify_channel_message_by_message_id(channel_id, message_id, replace_to)
                if is_success:
                    if not crawler.delete_channel_message_by_message_id(channel_id, message_id):
                        failed_count += 1
                else:
                    failed_count += 1

            pbar.update(len(messages))

        if total_results_size == 0:
            logging.info('')
            logging.info('There are no messages to bulky delete...')
            return

        oldest_message_id = int(message['id'])
        oldest_message_datetime = message['timestamp']

        logging.info('')
        logging.info(f'Done to bulky delete {total_results_size - failed_count} messages!')
        logging.info(f'Failed to modify or to delete {failed_count} messages.')
        logging.info(f'Message IDs: from {oldest_message_id} to {newest_message_id}')
        logging.info(f'Message Timestamps: from {oldest_message_datetime} to {newest_message_datetime}')
    except Exception as e:
        logging.info('')
        logging.warning('Aborted!')
        raise e


if __name__ == '__main__':
    main()

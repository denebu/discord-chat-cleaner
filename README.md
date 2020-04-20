# discord-chat-cleaner
A fast, easy-of-use Discord chat cleaner (bulk deleter) written in Python.

It supports three features:
 - *retry-if-rate-limited* feature will sleep and retry requests at most 5 times if rate limited. 
 - *modify-before-delete* feature will modify to random or given string before delete it.
 - **[NEW!]** Now, you can bulky delete DMs!

DISCLAIMER: Use at your own risk.

## Installation
Python 3.6+ is required.

```bash
$ git clone https://github.com/denebu/discord-chat-cleaner
$ cd discord-chat-cleaner
$ pip3 install -r requirements.txt
```

## Usage
For example,

```bash
$ python3 discord-chat-cleaner.py --room-id=12341234 --room-type=guild \
--author-id=56785678 --newest-message-id=12345678 --oldest-message-id=0 \
--replace-before-delete=random --default-sleep=0.2
Token: (input Discord user token here, invisible)
```

will do delete each message after modify it to random string (`bm5 .s kd34tlnqPIo`, say), sleeping 200ms.

I recommend to use `--default-sleep` flag to avoid frequent rate limits. `0.2` or greater is sufficient for me.

You can see help via `python3 discord-chat-cleaner.py --help`.

## Performance
This program can delete about 5500 messages during 100 minutes,
 using `--replace-before-delete=random` and `--default-sleep=0.2` flag.

## License
Original author is Deneb (https://github.com/denebu)

MIT License

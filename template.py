#!/usr/bin/env python3
# -*- coding: ascii -*-

# Simple basebot bot template.

import basebot

def maybe_exit(match, meta):
    # Ignore requests not directed at us.
    nickname = match.group(1)
    if not meta['self'].nick_matches(nickname): return
    # Otherwise, respond and exit.
    meta['reply']('/me exits')
    meta['self'].manager.shutdown()

def main():
    basebot.run_minibot(
        # Name of the bot for logging purposes. If in doubt, set it to the
        # same value as nickname.
        botname='TestingBot',
        # (Initial) nickname of the bot.
        nickname='TestingBot',
        # Text to respond with to a general !help command.
        #short_help='I am a testing bot.',
        # Text to respond with to a specific !help command.
        long_help='I am a testing bot. You can !kill me, and little more.',
        # Bot behavior be here.
        regexes={
            # Insert 'regex': response pairs here.
            # Keep this one in place.
            r'^!kill\s+@(\S+)\s*$': maybe_exit
        }
    )

if __name__ == '__main__': main()

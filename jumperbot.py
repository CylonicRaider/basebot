#!/usr/bin/env python3
# -*- coding: ascii -*-

import basebot

def jump_handler(match, meta):
    room = match.group(1)
    meta['reply']('/me jumps away...')
    meta['self'].set_roomname(room)

def main():
    basebot.run_minibot(botname='JumperBot', nickname='JumperBot',
        short_help='I jump into others rooms when commanded to.',
        long_help='"!jump &roomname" to make me jump there.',
        regexes={'^!jump\s+&?([a-z][a-z0-9]+)\s*$': jump_handler})

if __name__ == '__main__': main()

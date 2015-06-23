#!/usr/bin/env python3
# -*- coding: ascii -*-

# @tumbleweed -- Euphoria bot indicating silence by "rolling by".
#                Easter egg: "!conjure @tumbleweed" forces @tumbleweed
#                            to roll by unconditionally.
# This code is in the public domain.

import sys
import threading

import basebot

DELAY = 600.0

# Background thread initiating the roll-bys.
def waiter(inst, cond):
    with cond:
        while True:
            cond.wait(DELAY)
            if inst.has_message and not inst.conjure:
                inst.has_message = False
                continue
            if not inst.sent_comment or inst.conjure:
                inst.send_chat('/me rolls by', inst.lonely_message)
                inst.sent_comment = True
                inst.lonely_message = None
                inst.conjure = False

# Main class.
class TumbleWeed(basebot.ThreadedBot):
    NAME = 'TumbleWeed'
    NICK_NAME = 'tumbleweed'

    # Constructor. Not particularly interesting.
    def __init__(self, *args, **kwds):
        basebot.ThreadedBot.__init__(self, *args, **kwds)
        self.cond = threading.Condition()
        self.has_message = False
        self.sent_comment = False
        self.lonely_message = None
        self.conjure = False

    # Chat handler. Informs the background thread about new messages.
    def handle_chat(self, info, message):
        if info['sender'] == self.nickname: return
        if info['content'] == '!conjure @' + self.nickname:
            self.conjure = True
        with self.cond:
            self.has_message = True
            if self.sent_comment or self.conjure:
                self.lonely_message = info['id']
            else:
                self.lonely_message = None
            self.sent_comment = False
            self.cond.notifyAll()

    # Start-up method. Spawns the background thread.
    def startup(self):
        basebot.spawn_thread(waiter, self, self.cond)
        basebot.ThreadedBot.startup(self)

# Main function. Calls basebot.run_main()
def main():
    basebot.run_main(TumbleWeed, sys.argv[1:])

if __name__ == '__main__': main()

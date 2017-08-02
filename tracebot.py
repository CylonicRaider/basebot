#!/usr/bin/env python3
# -*- coding: ascii -*-

import sys, os
import basebot

class TraceBot(basebot.Bot):

    BOTNAME = 'TraceBot'
    NICKNAME = 'tracebot'

    def __init__(self, *args, **kwds):
        basebot.Bot.__init__(self, *args, **kwds)
        self.trace = kwds.get('trace', True)

    def send_raw(self, obj, retry=True):
        if self.trace and retry:
            sys.stderr.write('< %r\n' % (obj,))
            sys.stderr.flush()
        basebot.Bot.send_raw(self, obj, retry)

    def handle(self, packet):
        if self.trace:
            sys.stderr.write('> %r\n' % (packet,))
            sys.stderr.flush()
        basebot.Bot.handle(self, packet)

if __name__ == '__main__': basebot.run_main(TraceBot)

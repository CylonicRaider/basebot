#!/usr/bin/env python3
# -*- coding: ascii -*-

# @sudo -- (Humorous) Euphoria bot watching for messages starting with
#          "sudo", and responding with "Permission denied".

# For sys.argv; bot functionality.
import sys
import basebot

# Main function. Could be omitted (but I prefer not to do).
def main():
    # sys.argv[1:]: Argument tuple.
    # botname     : Name to use in logging.
    # nickname    : Actual nick-name.
    # regexes     : Mapping of regex-response pairs.
    basebot.run_minibot(sys.argv[1:], botname='SudoBot', nickname='sudo',
                        regexes={'^sudo\\b': '/me Permission denied.'})

if __name__ == '__main__': main()

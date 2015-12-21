#!/usr/bin/env python3
# -*- coding: ascii -*-

# @sudo -- (Humorous) Euphoria bot watching for messages starting with
#          "sudo", and responding with "Permission denied".

# Obligatory import.
import basebot

# Main function. Could be omitted (but I prefer not to do).
def main():
    # botname : Name to use in logging.
    # nickname: Actual nick-name.
    # regexes : Mapping of regex-response pairs.
    basebot.run_minibot(botname='SudoBot', nickname='sudo',
                        regexes={'^sudo\\b': '/me Permission denied.'})

if __name__ == '__main__': main()

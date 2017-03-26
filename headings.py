#!/usr/bin/env python3
# -*- coding: ascii -*-

import sys, datetime, json

def today():
    return datetime.date.today().isoformat()

# Read input.
data = json.load(sys.stdin)

# Process data (if not already done).
meta = data[0]['unMeta']
if not meta:
    # Update headings.
    remove = None
    for n, item in enumerate(data[1]):
        if item['t'] == 'Header':
            if item['c'][0] == 1:
                if remove is not None:
                    sys.stderr.write('ERROR: Input has more than one first '
                        'heading; aborting.\n')
                    sys.exit(1)
                remove = n
            else:
                item['c'][0] -= 1
    # Add title to metadata (if found).
    if remove is not None:
        title = data[1].pop(remove)
        meta['title'] = {'t': 'MetaInlines', 'c': title['c'][2]}
        meta['date'] = {'t': 'MetaInlines', 'c': [
            {'t': 'Str', 'c': today()}
        ]}

# Produce output.
json.dump(data, sys.stdout)

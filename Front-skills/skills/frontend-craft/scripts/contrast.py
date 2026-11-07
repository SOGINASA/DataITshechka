#!/usr/bin/env python3
"""Opaque sRGB hex contrast; no external dependencies or network."""
import argparse
import json
import re

def normalize(value):
    value = value.lstrip('#')
    if not re.fullmatch(r'(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})', value):
        raise ValueError('Use #RGB or #RRGGBB; alpha and named colors are not supported.')
    if len(value) == 3:
        value = ''.join(c * 2 for c in value)
    return '#' + value.upper()

def luminance(value):
    value = normalize(value)
    channels = [int(value[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in channels]
    return sum(a * b for a, b in zip(linear, (.2126, .7152, .0722)))

def contrast(a, b):
    low, high = sorted((luminance(a), luminance(b)))
    return (high + .05) / (low + .05)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('foreground')
    parser.add_argument('background')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    try:
        fg, bg = normalize(args.foreground), normalize(args.background)
    except ValueError as exc:
        parser.error(str(exc))
    ratio = contrast(fg, bg)
    result = {'foreground': fg, 'background': bg, 'ratio': round(ratio, 4),
              'normal_text_AA': ratio >= 4.5, 'large_text_AA': ratio >= 3,
              'scope': 'Opaque sRGB text pair only; not a page accessibility audit.'}
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f'{fg} on {bg}: {ratio:.2f}:1')
        print('Normal text AA: ' + ('PASS' if result['normal_text_AA'] else 'FAIL'))
        print('Large text AA: ' + ('PASS' if result['large_text_AA'] else 'FAIL'))
        print(result['scope'])
    return 0

if __name__ == '__main__':
    main()

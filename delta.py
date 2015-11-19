#!/usr/bin/env python

import re
import click
import sys
import time
import subprocess
import os
import colors
import string

class Format(object):
    def __init__(self, fmt, fmts, colors=True):
        self.fmt = fmt
        self.val_fmts = fmts
        self.colors = colors

    def __repr__(self):
        return self.fmt

    def colorize(self, val, fmt, use_colors=None, **kwargs):
        if use_colors is None: use_colors = self.colors
        s = fmt.format(val, **kwargs)
        if use_colors:
            if val > 0:
                return colors.green(s)
            elif val < 0:
                return colors.red(s)
        return s

    def format(self, *values, **kwargs):
        formatted_vals = [self.colorize(val, fmt, **kwargs) for fmt, val in zip(self.val_fmts, values)]
        return self.fmt.format(*formatted_vals)

    def format_str_with_spaces(self):
        last_seen = None
        fmt = []
        for c in self.fmt:
            if c == '{':
                if last_seen == '{': # escaped {
                    fmt.append(' ')
                    last_seen = None
                    continue
            elif c == '}':
                if last_seen == '}': # escaped }
                    fmt.append(' ')
                    last_seen = None
                    continue
                elif last_seen == '{': # real format str
                    fmt.append('{}')
                    last_seen = None
                    continue
            elif c in string.whitespace:
                fmt.append(c)
            else:
                fmt.append(' ')
            last_seen = c
        return ''.join(fmt)

    def format_wsp(self, *values, **kwargs):
        formatted_vals = [self.colorize(val, fmt, **kwargs) for fmt, val in zip(self.val_fmts, values)]
        return self.format_str_with_spaces().format(*formatted_vals)


class ValueFormat(object):
    def __init__(self, prefix, align, plus, width, fmt):
        self.prefix = prefix
        self.align = align
        self.plus = plus
        self.width = width
        self.fmt = fmt

    def format_str(self, prefix=None, align=None, plus=None, width=None, fmt=None):
        if prefix is None: prefix = self.prefix
        if align is None: align = self.align
        if plus is None: plus = self.plus
        if width is None: width = self.width
        if fmt is None: fmt = self.fmt
        return '%s{:%s%s%s%s}' % (prefix, align, plus, width, fmt)

    def format(self, *values, **kwargs):
        return self.format_str(**kwargs).format(*values)

formats = {}

def parse_num(match, plus, flex):
    spaces, n = match.groups()

    prefix = ''
    width = len(n)
    align = '<'

    if spaces:
        prefix = ' '
        width += len(spaces) - 1
        align = ''
    elif match.start(1) == 0:
        align = ''

    if '.' not in n:
        if align == '' and flex and width < 2:
            width = 2
        if len(n) > 1 and n.startswith('0'):
            width = '0{}'.format(width)
            align = ''

        return int(n), ValueFormat(prefix, align, plus, width, '')

    whole, frac = n.split('.', 1)
    frac_len = len(frac)
    if align == '' and flex and width < frac_len + 3:
        width = frac_len + 3
    if len(whole) > 1 and whole.startswith('0'):
        width = '0{}'.format(width)
        align = ''
    return float(n), ValueFormat(prefix, align, plus, width, '.%df' % len(frac))

def num(n):
    if '.' not in n:
        return int(n)
    return float(n)

def parse(line, flex=True):
    global formats
    values = []
    val_formats = []
    def value(v):
        val, fmt = parse_num(v, '+', flex)
        values.append(val)
        val_formats.append(fmt)
        return '{}'

    raw_fmt = line.replace('{', '{{').replace('}', '}}')
    raw_fmt = re.sub(r'(\s*)([0-9]+(?:\.[0-9]+)?)', value, raw_fmt)
    fmt = Format(raw_fmt, val_formats)

    rx_line = re.sub(r'([()\[\]^$\\])', r'\\\1', line)
    rx_str = re.sub(r'(\s*[0-9]+(?:\.[0-9]+)?)', r'(\s*[0-9]+(?:\.[0-9]+)?)', rx_line)
    rx = re.compile(rx_str)

    formats[rx] = (fmt, values)
    return fmt.format(*values, plus='', use_colors=False)


def process(line, flex):
    global formats
    for rx, (fmt, old_values) in formats.items():
        m = rx.match(line)
        if m:
            values = [num(v) for v in m.groups()]
            deltas = [n-o for n, o in zip(values, old_values)]
            formats[rx] = (fmt, values)
            return fmt, deltas, values

    return parse(line, flex), None, None


def stdin_feed(sep_interval):
    while True:
        ts = time.time()
        line = sys.stdin.readline()
        if not line:
            break
        yield line, (time.time() - ts) > sep_interval


def command_feed(cmd, interval):
    if len(cmd) == 1:
        shell = os.getenv('SHELL', '/bin/sh')
        cmd = (shell, '-c') + cmd
    while True:
        output = subprocess.check_output(cmd)
        first = True
        for line in output.splitlines():
            yield line + '\n', first
            first = False
        time.sleep(interval)


@click.command()
@click.option('-t', '--timestamps/--no-timestamps', help='Show timestamps on all output lines')
@click.option('-i', '--interval', metavar='SECONDS', type=click.INT,
    help='Interval between command runs', default=1)
@click.option('-f', '--flex/--no-flex', help='Tweak column widths for better output (default is on)', default=True)
@click.option('-s', '--separators/--no-separators', help='Show separators between chunks of output (default is on)', default=True)
@click.option('-c', '--color', type=click.Choice(['never', 'auto', 'always']), help='Color output', default='auto')
@click.option('-o', '--orig/--no-orig', help='Show original output interleaved with deltas')
@click.option('-z', '--skip-zeros/--with-zeros', help='Skip all-zero deltas')
@click.argument('cmd', nargs=-1, required=False)
def cli(timestamps, cmd, interval, flex, separators, color, orig, skip_zeros):
    if cmd:
        feed = command_feed(cmd, interval)
    else:
        feed = stdin_feed(interval * 0.8)

    if color == 'never':
        color = False
    elif color == 'always':
        color = True
    else:
        color = os.isatty(sys.stdout.fileno())

    def p(line, with_sep=False):
        if with_sep:
            if timestamps:
                sys.stdout.write(time.asctime() + '\n')
            else:
                sys.stdout.write('--- {}\n'.format(time.asctime()))
        if timestamps:
            sys.stdout.write('{}: '.format(time.asctime()))
        sys.stdout.write(line)
        sys.stdout.flush()

    try:
        print_sep = True
        for line, want_sep in feed:
            fmt, deltas, values = process(line, flex)
            if values is None:
                p(fmt)
                continue
            all_zeros = all(d == 0 for d in deltas)
            print_sep = print_sep or want_sep
            with_sep = separators and print_sep and len(formats) > 1
            if orig:
                print_sep = False
                if len(values):
                    p(fmt.format(*values, plus='', use_colors=False), with_sep=with_sep)
                    if not skip_zeros or not all_zeros:
                        p(fmt.format_wsp(*deltas, use_colors=color))
                else:
                    p(fmt.format(*values), with_sep=with_sep)
            else:
                if not skip_zeros or not all_zeros:
                    print_sep = False
                    p(fmt.format(*deltas, use_colors=color), with_sep=with_sep)

    except KeyboardInterrupt:
        pass
    except IOError:
        return

if __name__ == '__main__':
    cli()
